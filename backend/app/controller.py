import logging
import math
import threading
import time
from datetime import datetime, timezone

from .automation import Settings, MoistureFilter, number
from .hardware.gpio_controller import HardwareError
from .storage import BudgetExceeded, utc_now

log = logging.getLogger(__name__)


class ControlConflict(RuntimeError):
    """Another command owns the actuators."""


class WateringController:
    """Single process owner of actuators, sampling and automatic decisions."""

    def __init__(self, hardware, manual_timeout=60, store=None):
        if type(manual_timeout) is not int or not 1 <= manual_timeout <= 600:
            raise ValueError("MANUAL_TIMEOUT_SECONDS musi być liczbą całkowitą od 1 do 600.")
        self.hardware, self.manual_timeout, self.store = hardware, manual_timeout, store
        self._lock = threading.RLock()
        self._session = None
        self._last_result = self._error = None
        self._closed = False
        self._filter = MoistureFilter()
        self._latest = []
        self._sampled_at = None
        self._demand = False
        self._auto_reason = "disabled"
        self._soak_until = 0
        self._soaking = False
        self._sample_errors = {}
        self._service_stop = threading.Event()
        self._service_wake = threading.Event()
        self._service_thread = None
        channels = hardware.config.moisture_channels
        defaults = Settings(channel=channels[0] if channels else 0).json()
        self._scope = hardware.config.mode
        if store:
            defaults.update(store.settings(self._scope))
        self.settings = Settings(**defaults)
        self.settings.validate(channels, hardware.flow()["configured"])
        self._auto_reason = "collecting_samples" if self.settings.enabled else "disabled"
        if store:
            store.recover(hardware.simulated)
            finished = store.last_finished(hardware.simulated)
            if finished:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(finished.replace("Z", "+00:00"))).total_seconds()
                self._soak_until = time.monotonic() + max(0, self.settings.soak_seconds - elapsed)
                self._soaking = True
        if hardware.error:
            self._event("hardware_error", hardware.error)

    def _event(self, kind, message):
        if self.store:
            try:
                self.store.event(kind, message, self.hardware.simulated)
            except Exception:
                log.exception("Nie udało się zapisać zdarzenia")
                self._error = self._error or "Zapis historii jest niedostępny."

    def _ensure_ready(self):
        if self._closed or self._error or not self.hardware.ready:
            raise HardwareError(self._error or self.hardware.error or "Sprzęt jest niedostępny lub został wyłączony.")

    def _volume(self, session):
        flow = self.hardware.flow()
        pulses = max(0, flow["pulses"] - session["baseline_pulses"]) if flow["configured"] else None
        factor = session["pulses_per_liter"]
        ml = round(1000 * pulses / factor, 3) if pulses is not None and factor else None
        return pulses, ml

    def _finish(self, result):
        session = self._session
        if session:
            session["cancel"].set()
        errors = self.hardware.safe_off()
        if errors:
            self._error = "; ".join(errors)
        elif self.hardware.error:
            self._error = self._error or self.hardware.error
        self._session = None
        self._last_result = "failed" if self._error else result
        if session:
            self._soak_until = time.monotonic() + self.settings.soak_seconds
            self._soaking = True
            self._filter.clear()
            self._auto_reason = "soaking" if self.settings.enabled else "disabled"
            if result == "sensor_error":
                self._auto_reason = "waiting_for_valid_samples"
            if self.store and session["run_id"] is not None:
                try:
                    pulses, ml = self._volume(session)
                    self.store.finish_run(session["run_id"], self._last_result, self._error or session.get("error"),
                                          max(0, time.monotonic() - session["started"]), pulses, ml)
                except Exception:
                    log.exception("Nie udało się zapisać wyniku podlewania")
                    self._error = "Zapis historii jest niedostępny. Wyłączono pompę i zawór."
                    self._last_result = "failed"
                    errors.append(self._error)
        if self._error:
            self._auto_reason = "hardware_or_storage_error"
            self._event("control_error", self._error)
        return errors

    def _fail(self, exc):
        log.exception("Błąd sterowania urządzeniem")
        self._error = str(exc) if isinstance(exc, HardwareError) else "Błąd sterowania urządzeniem. Sprawdź dziennik serwera."
        self._finish("failed")
        raise HardwareError(self._error) from exc

    def _prepare(self, mode, seconds, source, target_ml=None):
        # Persist the reservation before energizing any actuator.
        run_id = None
        if self.store:
            try:
                run_id = self.store.begin_run(source, "volume" if target_ml is not None else mode,
                                              seconds, target_ml, self.hardware.simulated,
                                              self.settings.daily_limit_seconds if source == "automatic" else None)
            except BudgetExceeded:
                raise
            except Exception as exc:
                log.exception("Nie udało się zapisać rozpoczęcia podlewania")
                self._fail(HardwareError("Nie udało się zapisać rozpoczęcia podlewania. Sprawdź bazę danych."))
        now = time.monotonic()
        self._session = {"mode": mode, "source": source, "started": now, "deadline": now + seconds,
                         "seconds": seconds, "cancel": threading.Event(), "run_id": run_id,
                         "target_ml": target_ml, "pump_started": None,
                         "baseline_pulses": self.hardware.flow()["pulses"],
                         "pulses_per_liter": self.settings.flow_pulses_per_liter}
        return self._session

    def _launch(self, session):
        threading.Thread(target=self._wait_for_end, args=(session,),
                         name="watering-monitor", daemon=True).start()

    def _check_session(self, session):
        if self._session is not session:
            return
        now = time.monotonic()
        if self.hardware.error:
            self._error = self.hardware.error
            self._finish("failed")
            return
        flow = self.hardware.flow()
        pulses, ml = self._volume(session)
        if session["target_ml"] is not None and ml is not None and ml >= session["target_ml"]:
            self._finish("completed")
            return
        if flow["configured"] and session["pump_started"] is not None:
            last = max(session["pump_started"], flow["last_pulse"] or session["pump_started"])
            if now - last >= self.settings.no_flow_timeout_seconds or (now >= session["deadline"] and pulses == 0):
                self._error = "Nie wykryto przepływu podczas pracy pompy."
                self._finish("failed")
                return
        if now >= session["deadline"]:
            if session["target_ml"] is not None:
                self._error = "Nie osiągnięto zadanej objętości w wyznaczonym czasie."
            self._finish("completed" if session["mode"] == "watering" else "timeout")

    def _wait_for_end(self, session):
        while not session["cancel"].wait(0.05):
            with self._lock:
                if self._session is not session:
                    return
                self._check_session(session)

    def start(self, seconds, zone=0, target_ml=None, source="manual"):
        if type(seconds) is not int or not 1 <= seconds <= 600:
            raise ValueError("Czas podlewania musi być liczbą całkowitą od 1 do 600 sekund.")
        if type(zone) is not int or zone != 0:
            raise ValueError("Obsługiwana jest tylko strefa 0.")
        if target_ml is not None and not number(target_ml, 1, 5000):
            raise ValueError("Objętość musi być skończoną liczbą od 1 do 5000 ml.")
        with self._lock:
            self._ensure_ready()
            if self._session:
                raise ControlConflict("Inna sesja jest aktywna. Zatrzymaj ją przed rozpoczęciem podlewania.")
            if target_ml is not None and (not self.hardware.flow()["configured"] or not self.settings.flow_pulses_per_liter):
                raise ControlConflict("Podlewanie według objętości wymaga skonfigurowanego i skalibrowanego przepływomierza.")
            session = self._prepare("watering", seconds, source, target_ml)
            try:
                self.hardware.set_valve(True)
                self.hardware.set_pump(True)
                session["pump_started"] = time.monotonic()
                self._launch(session)
            except Exception as exc:
                self._fail(exc)
            return self._operation_status()

    def set_manual(self, device, on):
        with self._lock:
            self._ensure_ready()
            if self._session and self._session["mode"] == "watering":
                raise ControlConflict("Podlewanie trwa. Użyj przycisku „Zatrzymaj wszystko”, aby je przerwać.")
            state = self.hardware.status()
            if device == "pump" and on and state["valve_open"] is not True:
                raise ControlConflict("Otwórz zawór przed uruchomieniem pompy.")
            if device == "valve" and not on and state["pump_on"] is not False:
                raise ControlConflict("Zatrzymaj pompę przed zamknięciem zaworu lub użyj przycisku „Zatrzymaj wszystko”.")
            try:
                if on:
                    new_session = self._session is None
                    session = self._session or self._prepare("manual", self.manual_timeout, "manual")
                    action = self.hardware.set_pump if device == "pump" else self.hardware.set_valve
                    action(True)
                    if device == "pump" and session["pump_started"] is None:
                        session["pump_started"] = time.monotonic()
                    if new_session:
                        self._launch(session)
                else:
                    errors = self._finish("stopped")
                    if errors:
                        raise HardwareError(self._error)
            except Exception as exc:
                self._fail(exc)

    def stop(self):
        with self._lock:
            # Disable automation in memory before any I/O, so it cannot restart.
            self.settings.enabled = False
            self._demand = False
            self._auto_reason = "disabled"
            errors = self._finish("cancelled")
            if self.store:
                try:
                    self.store.save_settings(self._scope, self.settings.json())
                except Exception:
                    self._error = "Nie udało się zapisać wyłączenia automatyki. Sprawdź bazę danych przed ponownym uruchomieniem."
                    errors.append(self._error)
            if errors:
                raise HardwareError(self._error)
            return self._operation_status()

    def update_settings(self, patch):
        if not isinstance(patch, dict) or not patch or set(patch) - set(self.settings.json()):
            raise ValueError("Podaj obsługiwane pola ustawień w niepustym obiekcie JSON.")
        with self._lock:
            if self._session and patch != {"enabled": False}:
                raise ControlConflict("Zatrzymaj podlewanie przed zmianą ustawień lub kalibracji.")
            values = self.settings.json() | patch
            if values["channel"] != self.settings.channel and not {"dry_raw", "wet_raw"} <= patch.keys():
                values.update(dry_raw=None, wet_raw=None)
            updated = Settings(**values).validate(
                self.hardware.config.moisture_channels, self.hardware.flow()["configured"])
            if self.store:
                self.store.save_settings(self._scope, updated.json())
            self.settings = updated
            self._filter.clear()
            self._latest = []
            self._sampled_at = None
            self._demand = False
            self._auto_reason = "collecting_samples" if updated.enabled else "disabled"
            if not updated.enabled and self._session and self._session["source"] == "automatic":
                self._finish("cancelled")
            self._service_wake.set()
            return self.settings.json()

    def calibrate_flow(self, run_id, measured_ml):
        if type(run_id) is not int or run_id < 1 or not number(measured_ml, 1, 100000):
            raise ValueError("Podaj dodatni numer cyklu i zmierzoną objętość od 1 do 100000 ml.")
        with self._lock:
            run = self.store.run(run_id) if self.store else None
            if not run or run["simulated"] != self.hardware.simulated or run["status"] == "running" or not run["pulses"]:
                raise ValueError("Wybierz zakończony cykl z zapisanymi impulsami w bieżącym trybie sprzętu.")
            return self.update_settings({"flow_pulses_per_liter": 1000 * run["pulses"] / measured_ml})

    def _operation_status(self):
        session = self._session
        pulses, ml = self._volume(session) if session else (None, None)
        return {"active": session is not None, "mode": session["mode"] if session else "idle",
                "source": session["source"] if session else None,
                "remaining_seconds": max(0, math.ceil(session["deadline"] - time.monotonic())) if session else 0,
                "seconds": session["seconds"] if session else None, "zone": 0,
                "run_id": session["run_id"] if session else None,
                "target_ml": session["target_ml"] if session else None,
                "delivered_ml": ml, "pulses": pulses,
                "last_result": self._last_result, "error": self._error}

    def status(self):
        with self._lock:
            hardware = self.hardware.status()
            if hardware["error"] and self._session:
                self._error = hardware["error"]
                self._finish("failed")
                hardware = self.hardware.status()
            if self._error:
                hardware.update(ready=False, error=self._error)
            return {"hardware": hardware, "operation": self._operation_status(),
                    "automation": {"enabled": self.settings.enabled, "reason": self._auto_reason,
                                   "soak_remaining_seconds": max(0, math.ceil(self._soak_until - time.monotonic())),
                                   "daily_used_seconds": self.store.daily_used(self.hardware.simulated) if self.store else 0,
                                   "daily_limit_seconds": self.settings.daily_limit_seconds,
                                   "sampling_active": bool(self._service_thread and self._service_thread.is_alive())},
                    "flow": {"configured": self.hardware.flow()["configured"],
                             "calibrated": self.settings.flow_pulses_per_liter is not None,
                             "pulses_per_liter": self.settings.flow_pulses_per_liter}}

    def moisture(self):
        with self._lock:
            return {"hardware_available": self.hardware.available, "simulated": self.hardware.simulated,
                    "channels": self.hardware.config.moisture_channels,
                    "readings": self.hardware.read_moisture(),
                    "samples": list(self._latest), "sampled_at": self._sampled_at}

    def sample_once(self):
        with self._lock:
            if self._closed:
                return
            raw = self.hardware.read_moisture()
            self._sampled_at = utc_now()
            self._latest = [self._filter.sample(ch, raw[index] if index < len(raw) else None, self.settings)
                            for index, ch in enumerate(self.hardware.config.moisture_channels)]
            if self.store:
                try:
                    self.store.samples(self._latest, self.hardware.simulated, self._sampled_at)
                except Exception as exc:
                    log.exception("Nie udało się zapisać pomiarów czujników")
                    self._error = "Nie udało się zapisać pomiarów czujników. Sprawdź bazę danych."
                    self._finish("failed")
                    self._auto_reason = "storage_error"
                    return
            for sample in self._latest:
                error = sample["error"]
                if error and error != "Zbieranie nowych próbek." and error != self._sample_errors.get(sample["channel"]):
                    self._event("sensor_error", f"Kanał {sample['channel']}: {error}")
                self._sample_errors[sample["channel"]] = error
            self._decide()

    def _decide(self):
        if not self.settings.enabled:
            self._auto_reason = "disabled"
            return
        selected = next((s for s in self._latest if s["channel"] == self.settings.channel), None)
        if not selected or selected["moisture_percent"] is None or selected["error"]:
            if not selected or selected["error"] != "Zbieranie nowych próbek.":
                self._demand = False
            self._auto_reason = "waiting_for_valid_samples"
            if self._session and self._session["source"] == "automatic":
                self._session["error"] = "Pomiar wilgotności stał się niepoprawny."
                self._finish("sensor_error")
            return
        if self._error or not self.hardware.ready:
            self._auto_reason = "hardware_or_storage_error"
            return
        if self._session:
            self._auto_reason = "watering" if self._session["source"] == "automatic" else "manual_session"
            return
        if time.monotonic() < self._soak_until:
            self._auto_reason = "soaking"
            return
        if self._soaking:
            self._soaking = False
            self._filter.clear()
            self._auto_reason = "collecting_after_soak"
            return
        percent = selected["moisture_percent"]
        if percent >= self.settings.stop_percent:
            self._demand = False
        elif percent <= self.settings.start_percent:
            self._demand = True
        if not self._demand:
            self._auto_reason = "moisture_sufficient"
            return
        try:
            self.start(self.settings.portion_seconds, target_ml=(self.settings.portion_ml if self.settings.portion_mode == "volume" else None), source="automatic")
            self._auto_reason = "watering"
        except BudgetExceeded:
            self._auto_reason = "daily_limit"
        except (HardwareError, ControlConflict) as exc:
            self._auto_reason = str(exc)

    def start_sampling(self):
        with self._lock:
            if self._closed or self._service_thread is not None:
                return
            self._service_thread = threading.Thread(target=self._sample_loop, name="moisture-sampler", daemon=True)
            self._service_thread.start()

    def _sample_loop(self):
        while not self._service_stop.is_set():
            self._service_wake.clear()
            try:
                self.sample_once()
            except Exception as exc:
                log.exception("Nie udało się pobrać pomiarów")
                with self._lock:
                    self._error = "Nie udało się pobrać pomiarów. Sprawdź czujniki i dziennik serwera."
                    self._finish("failed")
            self._service_wake.wait(self.settings.sample_interval_seconds)

    def probe(self):
        with self._lock:
            return self.hardware.probe()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._service_stop.set()
            self._service_wake.set()
            self._finish("cancelled")
            self.hardware.close()
            self._closed = True
        if self._service_thread and self._service_thread is not threading.current_thread():
            self._service_thread.join(timeout=3)
