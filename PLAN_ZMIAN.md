# Plan zmian i dziennik realizacji

Ten plik jest trwałym zapisem ustaleń. Przy kontynuacji pracy należy najpierw
przeczytać ten plan, sprawdzić stan kodu i po zakończeniu zatwierdzonego zakresu
uzupełnić statusy, wyniki testów oraz ograniczenia.

## Uzgodniony zakres — 2026-09-22

Użytkownik zatwierdził punkty **1–5**, a następnie polecił rozpoczęcie **6–8**.
Dodatkowe propozycje pozostają poza zakresem, z wyjątkiem zmian koniecznych
do ukończenia zatwierdzonych funkcji.

## Punkty 1–5 — ukończone 2026-09-22

- [x] **1. Obsługa awarii i zatrzymywanie.** Zabezpieczyć uruchamianie całego
  cyklu; niezależnie wyłączać pompę i zamykać zawór po błędzie; ograniczyć czas
  ręcznego sterowania; dodać „Zatrzymaj wszystko” i sprzątanie przy zamknięciu.
- [x] **2. Jeden cykl podlewania naraz.** Zsynchronizować sterowanie; odrzucać
  kolidujące polecenia; wykonywać odliczanie poza żądaniem HTTP; udostępnić
  postęp i anulowanie; blokować powtórne kliknięcia w panelu.
- [x] **3. Wspólny adres panelu i API.** Serwować frontend z backendu,
  używać względnych adresów `/api`, poprawić uruchamianie lokalne i Docker.
- [x] **4. Diagnostyka i jawna symulacja.** Badać istniejące obiekty GPIO,
  obsługiwać brak sterownika i błędy inicjalizacji; rozróżniać symulację,
  gotowość i awarię; nie utożsamiać odczytu GPIO z fizycznym przepływem wody.
- [x] **5. Walidacja i jedna strefa.** Przyjmować rzeczywiste typy JSON,
  odrzucać ułamki i wartości logiczne jako czas; obsługiwać tylko strefę `0`;
  walidować konfigurację sprzętu.

## Punkty 6–8 — ukończone (oprogramowanie)

- [x] **6. Automatyczne podlewanie.** Kalibracja suchego/mokrego podłoża,
  filtrowanie pomiarów, progi i histereza, podlewanie porcjami, przerwa na
  wsiąknięcie, limit dzienny i blokada przy błędnym pomiarze.
- [x] **7. Przepływomierz.** Obsługa impulsów, kalibracja, objętość w ml,
  podlewanie zadanej ilości, limit czasu i wykrywanie braku przepływu.
  Szczegóły dobrać do rzeczywiście posiadanego sprzętu.
- [x] **8. Historia i baza danych.** Pomiary niezależne od przeglądarki,
  zapis cykli i błędów, API historii, wykresy, aktualizacje schematu bez
  kasowania danych. `init-db` obecnie zachowuje dane (dawniej usuwało tabele).

## Dodatkowe propozycje z przeglądu — poza zatwierdzonym zakresem

- [ ] Panel: ujednolicenie całego interfejsu w języku polskim.
  Skalibrowaną wilgotność i czas ostatniego pomiaru wdrożono w 6–8;
  postęp cyklu, blokady sterowania i aktualny stan połączenia w 1–5.
- [ ] Uwierzytelnienie poleceń sterujących urządzeniem.
- [ ] Wdrożenie na Raspberry Pi: dostęp kontenera do GPIO/SPI, dobór backendu
  GPIO, polaryzacja przekaźników i docelowy serwer aplikacji.
  Sprzątanie podczas zamykania procesu należy do punktu 1.
- [ ] Ujednolicenie zależności, działający Swagger/OpenAPI i dalsze porządki
  dokumentacji. Instrukcje zmienionego uruchamiania oraz testy awarii
  i współbieżności są częścią punktów 1–5.

## Dziennik

### 2026-09-22 — przegląd i rozpoczęcie

- Przeczytano kod, konfigurację, README, listę komponentów, PDF i sprawozdanie.
- Stan wyjściowy: **6 testów zaliczonych, 3 sprzętowe pominięte**.
- Symulacja potwierdziła: otwarty zawór po błędzie pompy, konflikt dwóch cykli,
  konflikt diagnostyki z zajętymi GPIO i błędną walidację czasu/stref.
- Potwierdzono brak wspólnego adresu panelu/API oraz odpowiedzi 404 Swaggera.
- Rozpoczęto realizację 1–5. Nie uruchamiano fizycznych urządzeń.

### 2026-09-22 — zakończenie punktów 1–5

**Wdrożono i sprawdzono:**

1. `backend/app/controller.py` jest jedynym właścicielem sesji sterowania.
   Start i stop obsługują błędy, a wyłączenie pompy i zamknięcie zaworu są
   podejmowane niezależnie. Błąd sterowania blokuje następne uruchomienia do
   usunięcia przyczyny i restartu aplikacji. `POST /api/stop` oraz przycisk
   „Zatrzymaj wszystko / Stop all” pozostają dostępne przy awarii.
   Ręczna sesja trwa maksymalnie `MANUAL_TIMEOUT_SECONDS` (domyślnie 60 s),
   licząc od otwarcia zaworu; kolejne polecenia ON nie wydłużają limitu.
   Obsłużono SIGINT/SIGTERM, zwalnianie GPIO i blokadę późnej inicjalizacji
   podczas zamykania. Wyłączono reloader/debugger w dostarczonym runnerze.
2. Cykl działa w tle i zwraca `202 Accepted`; jego postęp, wynik i błąd są
   dostępne w `/api/status`. Blokada obejmuje cykle i ręczne przełączniki,
   konflikty zwracają 409. Stary anulowany wątek nie może wyłączyć nowego cyklu.
   Ręczne uruchomienie pompy wymaga otwartego zaworu; jej zatrzymanie zamyka
   także zawór. Panel blokuje kolidujące kliknięcia i odświeża stan połączenia.
3. Flask serwuje panel, zasoby i API. Lokalnie adres to
   `http://localhost:5000/`, w Compose `http://localhost:8080/`.
   Usunięto osobny serwer statyczny, `frontend/config.js` i `API_BASE`.
   Docker uruchamia jeden proces Python przez `exec`, przekazując mu sygnały.
4. Dodano `HARDWARE_MODE=real|simulation` (domyślnie `real`). Brak GPIO daje
   czytelny błąd i odpowiedź 503 na start, bez automatycznej symulacji.
   Symulacja nie otwiera GPIO ani nie fabrykuje pomiarów. Diagnostyka HTTP
   odczytuje już posiadane urządzenia, nie rezerwuje ponownie pinów i jawnie
   zaznacza, że nie potwierdza fizycznego działania/przepływu.
   Obsłużono sprzątanie częściowo zainicjalizowanego sprzętu.
5. API wymaga rzeczywistych typów JSON: czas to liczba całkowita 1–600,
   strefa wyłącznie całkowite `0`, przełączniki to `true`/`false`.
   Konfiguracja odrzuca błędne/powtórzone kanały ADC, niepoprawne lub wspólne
   piny oraz kolizje pinów wykonawczych ze SPI. Panel pokazuje rzeczywiste
   numery skonfigurowanych kanałów.

Dodano `AGENTS.md`, kierujący kolejne sesje do tego planu. Zaktualizowano README
z uruchamianiem, semantyką API, testami i ograniczeniami. Baza danych, automatyka
i przepływomierz nie zostały rozbudowane.

**Weryfikacja:**

- Python: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`
  → **82 zaliczone, 3 sprzętowe pominięte**.
- Frontend: `node frontend/tests/app.test.cjs` → **6 zaliczonych**.
- `git diff --check`, `bash -n docker/entrypoint.sh` i
  `docker compose config --quiet` — bez błędów.
- Rzeczywisty serwer HTTP w symulacji: panel, zasoby, API, asynchroniczny start
  i zamknięcie przez SIGTERM — poprawne.
- Zbudowano obraz `watering-points-1-5:local`; w tymczasowym kontenerze sprawdzono
  panel, API, diagnostykę, podlewanie, STOP i zakończenie przez SIGTERM
  z kodem 0. Kontener testowy usunięto.

**Ograniczenia i środowisko:**

- Nie testowano fizycznego Raspberry Pi, pompy, zaworu ani czujników.
  Timeout w Pythonie nie zastępuje sprzętowego zabezpieczenia przy utracie
  zasilania, SIGKILL, zawieszeniu procesu lub awarii przekaźnika.
- Lokalny Docker ma niesprawny most `docker0`. Obraz zbudowano przez
  `docker build --network=host -t watering-points-1-5:local .`, a test wykonano
  z `--network=none` i żądaniami HTTP wewnątrz kontenera. Konfiguracji systemu
  nie zmieniano. Publikowanie portów przez lokalny most wymaga jego naprawy.
- Nadal obowiązuje jeden proces/właściciel GPIO. Uwierzytelnienie, serwer
  produkcyjny, konfiguracja sprzętu w Dockerze i polaryzacja przekaźników
  pozostają w dodatkowych propozycjach.
- **Punkty 6–8 nie zostały rozpoczęte. Następny etap wymaga polecenia użytkownika.**

### Kolejna sesja — rozpoczęcie punktów 6–8

- Użytkownik zatwierdził implementację automatyki, przepływomierza i historii.
- Automatyka domyślnie wyłączona; wymaga kalibracji czujnika i jawnego włączenia.
- Model przepływomierza nie jest jeszcze ustalony: GPIO i przelicznik impulsów
  będą konfigurowalne, bez zgadywania parametrów rzeczywistego urządzenia.
- Migracje mają zachować dotychczasowe dane; testy tylko z symulacją/mockami.

### Kolejna sesja — zakończenie punktów 6–8

**Aktualny stan: punkty 1–8 ukończone w kodzie.** Poniższy zapis zastępuje
wcześniejsze notatki o oczekiwaniu na zgodę na 6–8. Nie powtarzać tych etapów.

#### 6. Automatyka

- Dodano `backend/app/automation.py`: kalibrację suchego/mokrego podłoża
  obsługującą obie polaryzacje, medianę z nieparzystej liczby próbek i walidację.
- Automatyka jest domyślnie wyłączona. Panel umożliwia zapis kalibracji,
  przechwycenie rzeczywistego odczytu, ustawienie progów, porcji i limitów.
- Po przekroczeniu dolnego progu podlewa porcjami aż do górnego progu.
  Między porcjami odczekuje czas wsiąkania i zbiera nowy pełny zestaw próbek.
- Brak pomiaru, wartości niefinitywne i nasycenie ADC blokują automatykę;
  błąd wybranego czujnika podczas automatycznego cyklu zatrzymuje podlewanie.
- Dzienny budżet czasu (doba UTC) jest rezerwowany w SQLite przed włączeniem
  urządzeń. Liczą się pełne limity wszystkich cykli, także ręcznych, nieudanych
  i anulowanych. Budżet blokuje nowe cykle automatyczne; jawne sterowanie ręczne
  nadal może go przekroczyć. Rezerwacje przeżywają restart.
- STOP wyłącza automatykę również w zapisanych ustawieniach. Zwykłe zamknięcie
  procesu zachowuje jej ustawienie; po restarcie wymagane są przerwa i świeże
  próbki. Zmiana kanału wymaga nowej kalibracji.

#### 7. Przepływomierz

- Dodano opcjonalne `FLOW_PIN` oraz `FLOW_PULL_UP=1|0`; piny podlegają kontroli
  kolizji z pompą, zaworem i SPI. Impulsy z `DigitalInputDevice` są zliczane
  w krótkim callbacku niezależnym od blokad kontrolera i bazy.
- Obsługiwany jest współczynnik impulsów/litr oraz wyliczenie kalibracji z
  zakończonego cyklu i objętości rzeczywiście zmierzonej miarką.
- `POST /api/water` przyjmuje opcjonalne `volume_ml`; nadal wymaga `seconds`
  jako bezwzględnego limitu czasu. Dodano formularz podlewania w ml oraz
  podgląd liczby impulsów i podanej objętości.
- Cel objętości wymaga skonfigurowanego i skalibrowanego przepływomierza.
  Bez kalibracji można zliczać impulsy w cyklu czasowym; objętość jest `null`.
- Brak impulsów podczas pracy pompy, także w trybie ręcznym, zatrzymuje układ.
  Krótki cykl kończący się bez ani jednego impulsu jest oznaczony jako błąd.
  Przekroczenie czasu przed osiągnięciem objętości również jest błędem.
- Parametry rzeczywistego modelu nie zostały podane — nie wpisano zgadywanego
  GPIO ani przelicznika. Wymagają konfiguracji i kalibracji na sprzęcie.

#### 8. Historia i migracje

- `backend/app/storage.py` zarządza połączeniami SQLite, migracją transakcyjną,
  zapisami, ustawieniami, budżetem i paginacją historii.
- Stare tabele `moisture_readings` i `water_events` pozostają nietknięte;
  ich rekordy są jednorazowo importowane do nowych tabel. Stare cykle mają
  status `legacy`, bez dopisywania nieznanej objętości czy wyniku.
- `init-db` jest bezpieczne do ponownego wykonania; nie usuwa historii.
- Sampler startuje razem z runnerem, bez żądań HTTP i otwartej przeglądarki.
  Zapisuje surowe/skalibrowane odczyty, braki i błędy. Rejestrowane są także
  cykle, rezerwowane limity czasu, rzeczywisty czas sesji, impulsy i objętość.
- Po restarcie niedokończone rekordy są oznaczane `interrupted`; budżet nie
  jest zerowany i poprzedni cykl nie jest wznawiany. Błędy zapisu blokują
  uruchomienie bez rezerwacji lub powodują zatrzymanie po ich wykryciu.
- Ustawienia i historia rzeczywistego sprzętu/symulacji są rozdzielone.
- Dodano API ustawień, kalibracji i historii oraz panel z wykresem wilgotności,
  tabelą cykli i zdarzeniami. Wykres pokazuje ostatnie 300 próbek w wybranym
  zakresie; przerwy oznaczają niepoprawne/brakujące dane. API udostępnia
  stronicowanie starszych danych. Daty w panelu są lokalne, w bazie UTC.

**Weryfikacja końcowa:**

- Python: **144 zaliczone, 3 sprzętowe pominięte**.
- Frontend: **12 zaliczonych** (`app.test.cjs` i `features.test.cjs`).
- Kontrole składni JavaScript i skryptu startowego, `docker compose config`
  oraz `git diff --check` — poprawne.
- Zbudowano `watering-points-6-8:local` przez `docker build --network=host`.
- W tymczasowym kontenerze bez GPIO i sieci zewnętrznej sprawdzono: zasoby
  panelu, pomiary bez przeglądarki, zapis ustawień, cykl czasowy, STOP,
  zamknięcie SIGTERM, restart z zachowaniem historii i budżetu, odzyskiwanie
  przerwanego rekordu oraz ponowne `init-db` bez utraty danych.
  Kontener testowy został usunięty.

**Pozostaje na etapie uruchomienia sprzętu:**

- Podać model/przelicznik/GPIO przepływomierza, zweryfikować sygnały elektryczne,
  wykonać kalibrację czujnika wilgotności i przepływu oraz próby fizyczne.
  Nie uruchamiano żadnego rzeczywistego GPIO ani urządzeń wykonawczych.
- Objętość ma rozdzielczość jednego impulsu. Kontrola co 50 ms i opóźnienie
  fizycznego wyłączenia mogą powodować przekroczenie celu; dobrać porcje
  i przepływomierz do rzeczywistych warunków.
- Baza nie usuwa automatycznie starych rekordów. Produkcyjne uwierzytelnienie,
  docelowy serwer, fizyczne zabezpieczenia i lokalny most `docker0` nadal
  wymagają osobnych prac zgodnie z dodatkowym planem.
