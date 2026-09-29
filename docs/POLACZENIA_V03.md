# Połączenia i uruchomienie zestawu v0.3

Profil: RPi 4B, MCP3008 SPI0 CE0, SEN0193 na CH0, pompa Adafruit 1150
12 V, sterownik SparkFun COM-23979, pływak RSF54Y100RC; bez elektrozaworu
ani przepływomierza. To instrukcja projektowa, nie protokół wykonanego montażu.
Stan dokumentacji: 2026-09-29. Konfiguracja: `config/greenhouse.env.example`.

## Połączenia sygnałowe

W konfiguracji używamy numerów **BCM**, nie numerów fizycznych złącza RPi.
Numery nóżek MCP3008 poniżej dotyczą obudowy 16-pin; na module kieruj się
nazwami sygnałów i dokumentacją konkretnej płytki.

| Sygnał urządzenia | BCM / pin fizyczny RPi | Połączenie |
| --- | --- | --- |
| MCP3008 VDD (16), VREF (15) | 3,3 V / pin 1 | Zasilanie i odniesienie ADC |
| MCP3008 AGND (14), DGND (9) | GND / np. pin 6 | Wspólna masa |
| MCP3008 CLK (13) | BCM11 / pin 23 | SPI0 SCLK |
| MCP3008 DOUT (12) | BCM9 / pin 21 | SPI0 MISO |
| MCP3008 DIN (11) | BCM10 / pin 19 | SPI0 MOSI |
| MCP3008 CS/SHDN (10) | BCM8 / pin 24 | SPI0 CE0 |
| SEN0193 VCC, GND, AOUT | 3,3 V, GND, MCP3008 CH0 (1) | Jeden kanał gleby |
| SparkFun CTL | BCM17 / pin 11 | Sterowanie active low |
| SparkFun GND, strona sterowania | GND / np. pin 9 | Masa wspólna z RPi |
| Pływak, przewód 1 | BCM24 / pin 18 | Wejście z programowym pull-up do 3,3 V |
| Pływak, przewód 2 | GND / np. pin 20 | Styk bezpotencjałowy |

Pin fizyczny **24 (SPI CE0)** i **BCM24 (pływak, fizyczny 18)** to różne
połączenia. Zawór jest wyłączony w profilu, więc BCM27 nie jest rezerwowany.

Mapowanie SPI i poziomy GPIO opisuje [dokumentacja Raspberry Pi](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).
Nóżki i zakres zasilania ADC: [karta MCP3008, Microchip](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/21295d.pdf).
Sonda pracuje z zasilaniem 3,3–5,5 V; w tym zestawie stosujemy 3,3 V.
Podłączaj według oznaczeń, nie samych kolorów przewodów.
Źródło: [SEN0193, DFRobot](https://wiki.dfrobot.com/sen0193).

## Pompa i zasilanie

RPi zasilaj przez odpowiedni zasilacz USB-C. Pompę zasilaj osobno napięciem
12 V przez tor mocy SparkFun, z bezpiecznikiem i przewodami dobranymi do
obciążenia. Plus/minus pompy trafiają na złącze LOAD według oznaczeń płytki;
ujemnego zacisku obciążenia nie zwieraj do wspólnej masy — ominęłoby to
przełącznik low-side. Silnika nie zasilaj z GPIO ani przez płytkę stykową.

`PUMP_ACTIVE_HIGH=0`: niski stan CTL uruchamia obciążenie, wysoki wyłącza.
Moduł ma podciąganie CTL; jego wyjścia 3V3 nie łącz z zasilaniem 3,3 V RPi,
które ma własny regulator. Zachowanie przy wyłączonym RPi i zasilonym module,
rozruch, restart oraz OFF wymagają pomiarów na docelowym układzie (ELE-02).
Źródła: [SparkFun — sterowanie i podciąganie CTL](https://docs.sparkfun.com/SparkFun_MOSFET_Power_Switch_and_Buck_Regulator_Low-Side/single_page/),
[SparkFun — podłączenie obciążenia i zasilania](https://docs.sparkfun.com/SparkFun_MOSFET_Power_Switch_and_Buck_Regulator_Low-Side/hardware_hookup/).

Pompa [Adafruit 1150](https://www.adafruit.com/product/1150) jest modelem 12 V.
Nie wpisujemy jej katalogowej wydajności jako kalibracji. Wężyk, wysokość
podawania i zasilanie wpływają na szacunek dawki; potrzebny jest pomiar miarką.
Brak zaworu wymaga osobnego sprawdzenia samoczynnego wypływu i szczelności.

## Pływak i reakcja na awarię

Zamontuj pływak tak, aby **obecność wody zamykała styk do GND**, a spadek
poniżej minimum go otwierał. Przed podłączeniem sprawdź to omomierzem dla obu
położeń. Producent dopuszcza odwrócenie działania przez odwrócenie pływaka:
[karta producenta Cynergy3 RSF50, kopia u dystrybutora](https://www.mouser.com/datasheet/2/657/cynergy3_rsf50_v2-1892378.pdf).

Otwarty styk, przerwany przewód i nieznany odczyt blokują start. Utrata wody
podczas pracy wyłącza wyjścia w nadzorze co około 50 ms, niezależnie od SQLite.
Historia zapisuje `low_water`. Zwarcie przewodu do GND lub zablokowanie styku
w pozycji zamkniętej może wyglądać jak obecność wody; to wejście nie wykrywa
wszystkich awarii. Nie podawaj na nie 5 V ani 12 V.

## Uruchomienie i kalibracja

1. Zainstaluj zależności według README. W katalogu projektu załaduj profil:

   ```bash
   set -a
   source config/greenhouse.env.example
   set +a
   .venv/bin/python backend/run.py
   ```

2. Profil startuje w symulacji. Automatyka w nowej bazie jest wyłączona.
   Pływak ma stan nieznany, więc start jest celowo blokowany. Odczyty i obecność
   wody nie są wymyślane. MockFactory służy do testów, nie do kalibracji urządzenia.
3. Przed pracą z wodą sprawdź połączenia, napięcia i OFF. Na RPi włącz SPI0
   w konfiguracji systemu i zapewnij użytkownikowi dostęp do GPIO/SPI. Dopiero
   po tych kontrolach ustaw świadomie `HARDWARE_MODE=real` w lokalnej kopii
   profilu. Uruchamiaj jeden proces aplikacji, bez reloadera. Domyślny Compose
   nie udostępnia urządzeń GPIO/SPI i nie jest gotowym wdrożeniem sprzętowym.
4. Skalibruj suchy/mokry odczyt SEN0193 w docelowym podłożu. Sam odłączony
   przewód analogowy może dawać pozornie poprawny wynik — KOD-10 pozostaje
   do sprawdzenia fizycznego.
5. Wykonaj krótki cykl czasowy do poprawnego zakończenia, zbierz wodę do miarki.
   W formularzu kalibracji pompy wpisz ID cyklu i zmierzone ml. Wydajność jest
   wyliczana z faktycznego czasu załączenia pompy; cykle przerwane, błędne,
   ręczne przełączanie i cykle objętościowe są odrzucane.
6. Sprawdź powtarzalność w osobnej serii pomiarów. Panel pokazuje osobno
   szacunek i pomiar przepływomierza. W tym profilu pomiar przepływomierza
   pozostaje nieznany, a tryb podlewania wymagający tego pomiaru jest zablokowany.

Budżet obejmuje wszystkie tryby, rezerwuje pełny limit przed startem i nie
zwraca go po STOP. Doba UTC zaczyna się o 01:00/02:00 czasu polskiego.
Restart zachowuje budżet i nie wznawia niedokończonej sesji. Przed włączeniem
automatyki dobierz porcje, przerwy i limity na podstawie prób docelowego zestawu.
