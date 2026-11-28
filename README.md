# Tauron Virtual Meter — wersja 0.0.8

<img src="custom_components/tauron_virtual_meter/brand/icon@2x.png" alt="Ikona Tauron Virtual Meter — licznik energii z akcentami magenta" width="128" height="128">

Niestandardowa integracja Home Assistant: wirtualny licznik energii pobranej
i oddanej, w kWh, z historią godzinową przypisaną bezpośrednio do encji.
Nie tworzy osobnego źródła `tauron_importer` i nie wymaga panelu Energia.

**Stan: prototyp do weryfikacji na koncie eLicznik.** Testy lokalne sprawdzają
przeliczanie profili i scenariusze importu. Nie wykonano logowania na rzeczywiste
konto ani testu w działającym Home Assistant. Nie pobrano jeszcze Twoich danych.
Transport oparto na aktualnym kodzie Tauron AMIplus, lecz odpowiedzi różnych
liczników i ograniczenia historyczne API trzeba sprawdzić w praktyce.

## Instalacja

**Aktualizacja do 0.0.8:** zainstaluj wydanie i uruchom ponownie cały Home Assistant.
Jeśli wykluczenia obu sensorów w Recorderze zostały już ustawione, nie trzeba
ich zmieniać. Przy pierwszej instalacji lub aktualizacji ze starszych wersji
wykonaj [jednorazowe ustawienie Recordera](#jednorazowe-ustawienie-recordera).
Nie usuwaj statystyk, wpisu integracji ani lokalnego archiwum i nie rozpoczynaj
importu od nowa. Po wznowieniu synchronizacji integracja ponownie sprawdzi ostatni
tydzień, aby uzupełnić dostępne w Tauronie opóźnione pomiary.
Wersja 0.0.8 zapisuje wspólną przerwę po limicie logowań lub HTTP 429.
Próby uruchomienia integracji, synchronizacja i import historii nie kontaktują
się z Tauronem przed terminem `api_retry_after`, również po restarcie HA.
Lokalny termin ponowienia nie gwarantuje odblokowania konta przez Tauron.
Archiwum nadal znajduje się w `/config/.storage/tauron_virtual_meter/`;
aktualizacja ze starszych wersji automatycznie przenosi pliki do tego katalogu.
Szczegóły zmian znajdują się w [historii zmian](CHANGELOG.md).

[![Dodaj repozytorium do Home Assistant przez HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=direk&repository=tauron-virtual-meter&category=integration)

Kliknij przycisk, wybierz swój Home Assistant i potwierdź dodanie repozytorium
w HACS. Następnie zainstaluj integrację i uruchom ponownie Home Assistant.
Przycisk wymaga skonfigurowanego HACS.

Paczka instalacyjna: [wydanie 0.0.8](https://github.com/direk/tauron-virtual-meter/releases/tag/v0.0.8).
Rozpakuj plik `tauron_virtual_meter-0.0.8.zip`, a następnie:

1. Skopiuj katalog `custom_components/tauron_virtual_meter` do
   `/config/custom_components/tauron_virtual_meter` na urządzeniu z Home Assistant.
2. Uruchom ponownie Home Assistant.
3. W Ustawienia → Urządzenia i usługi → Dodaj integrację wybierz **Tauron Virtual Meter**.
4. Zaloguj się kontem **eLicznik**, wybierz licznik oraz zakres przeszukiwania.
   Dla kolejnych liczników dodaj osobne wpisy integracji.
5. W urządzeniu integracji sprawdź identyfikatory obu sensorów i dodaj je do
   `recorder.exclude.entities` zgodnie z [instrukcją poniżej](#jednorazowe-ustawienie-recordera).
   Ten krok jest wymagany także przy pierwszej instalacji.
6. Uruchom ponownie cały Home Assistant i sprawdź w atrybutach obu sensorów:
   `recorder_exclusion_required: false` oraz `state_class: total`.

Wymagany jest współczesny Home Assistant z `recorder`, interfejsem
`async_import_statistics` oraz metadanymi `mean_type`/`unit_class`.
Minimalna obsługiwana wersja HA nie została jeszcze ustalona testem uruchomieniowym.

Możesz też dodać `https://github.com/direk/tauron-virtual-meter` do HACS
jako repozytorium niestandardowe typu **Integracja** i zainstalować stamtąd.
Instalacja przez HACS nie była jeszcze sprawdzana w działającym HA.

### Jednorazowe ustawienie Recordera

**Wymagane przy świeżej instalacji oraz aktualizacji z wersji starszej niż 0.0.6.**
Jeśli wykluczenia już istnieją, nie trzeba ich ustawiać ponownie.
Dla każdego licznika należy jednorazowo wyłączyć **automatyczne** zapisywanie
sensorów energii pobranej i oddanej w Recorderze. Integracja sprawdza filtr i dopiero wtedy ustawia
`state_class: total`. Samo dodanie klasy bez wykluczenia naliczałoby opóźnione
odczyty według czasu pobrania. Import statystyk godzinowych nadal działa pod tymi
samymi identyfikatorami i datami pomiarów.

W `configuration.yaml` dodaj poniższe wykluczenia, zastępując identyfikatory
rzeczywistymi identyfikatorami obu swoich sensorów:

```yaml
recorder:
  exclude:
    entities:
      - sensor.twoja_encja_energia_pobrana
      - sensor.twoja_encja_energia_oddana
```

Połącz je z istniejącą sekcją `recorder`, jeśli ją masz; nie twórz drugiej.
Uruchom ponownie cały HA. Atrybut `recorder_exclusion_required: false` potwierdza,
że integracja widzi wykluczenie; w atrybutach będzie też `state_class: total`.
Wykluczenia pozostają po kolejnych synchronizacjach, restartach i aktualizacjach.
Jeśli zmienisz identyfikator sensora albo dodasz kolejny licznik, zaktualizuj listę.
Jeśli wcześniej dodano `state_class` dla tych sensorów w `homeassistant.customize`,
usuń tylko te wpisy klasy: od 0.0.6 ustawia je integracja.
Nie jest potrzebne wyłączenie całej integracji ani domeny `sensor` w Recorderze.
Integracja nie dodaje wykluczeń samodzielnie do globalnej
konfiguracji Recorder. Szczegóły: [filtry Recorder](https://www.home-assistant.io/integrations/recorder/#configure-filter).

## Historia tej samej encji

Integracja tworzy encje „Energia pobrana” i „Energia oddana”. Dokładne identyfikatory
znajdziesz w urządzeniu; HA nadaje je podczas instalacji.

Każda encja otrzymuje natywne statystyki godzinowe pod **własnym `entity_id`**.
Ich `state` to narastający wirtualny stan licznika, a `sum` to suma dostępnej energii.
Początek licznika to umowne zero przed pierwszym dostępnym pomiarem. Nie jest to
fizyczny stan rejestru na liczniku Taurona. Oryginalne rejestry są archiwizowane
oddzielnie, bez zgadywania godzin, do których się odnoszą.

Wersje do 0.0.5 nie deklarowały `state_class`, mimo importowania natywnych
statystyk. Powoduje to komunikat HA o usunięciu klasy stanu. Nie potwierdzaj
usuwania statystyk: to wada integracji, nie powód do kasowania historii.
Wykluczenie i obsługa klasy w nowym kodzie naprawiają tę sprzeczność.

Podczas skanowania pobrana suma jest
dostępna w atrybucie `downloaded_energy_kwh`; `value_is_partial: true` oznacza,
że pobieranie okresu jeszcze trwa. Główny stan jest wtedy `unknown` przy pierwszym
imporcie albo zachowuje poprzednią wartość podczas ponownego skanowania działającej
encji. Dopiero po zakończeniu skanowania publikowany jest stan licznika oraz
pełna pobrana historia godzinowa. Dzięki temu przyrost sumy podczas dopisywania
starszych dni nie udaje nowego zużycia w zwykłej Historii.
Puste odpowiedzi nie kończą wyszukiwania.

Atrybuty diagnostyczne encji (Narzędzia deweloperskie → Stany):

- `history_scan_next_day` — dzień, od którego będzie kontynuowany import.
- `history_days_remaining` — liczba dni pozostałych do sprawdzenia.
- `downloaded_interval_count` — liczba poprawnie odczytanych godzin dla tej encji.
- `empty_profile_day_count` — liczba pobranych pustych dób dla tej encji
  (np. same wartości `null`); nie są one uznawane za zerowe zużycie.
- `first_available_measurement` — najstarszy dotąd znaleziony pomiar tej encji;
  podczas importu może się cofać. Po zakończeniu dotyczy całego sprawdzonego zakresu.
- `history_discovery_enabled` — czy włączono sprawdzanie dostępności miesięcznej.
- `history_skipped_month_count`, `history_skipped_day_count` — liczba miesięcy
  i dni pominiętych po rozpoznaniu braku odczytów dla obu kierunków.
- `last_availability_month`, `last_availability_result` — ostatni sprawdzony miesiąc
  i wynik (`empty`, `available` albo `unknown`) dla poboru i oddania.
- `downloaded_energy_kwh` — suma dotychczas pobranych pomiarów; podczas importu
  może rosnąć wskutek dodawania starszych dni i nie oznacza bieżącego zużycia.
- `recovered_profile_count` — liczba zapisanych profili poboru/oddania odzyskanych
  lub ponownie przetworzonych po poprawkach parsera (łącznie dla obu encji).
- `last_history_attempt` — ostatnia próba pobrania archiwum.
- `last_history_error` i `history_retry_after` — powód oraz czas ponowienia po błędzie.
- `history_retry_kind` — `connection` oznacza chwilową awarię połączenia,
  `rate_limit` ograniczenie Taurona, `api_error` inny błąd API,
  a `authentication` konieczność ponownego logowania.
- `profile_issue_count` i `last_profile_issue` — problemy z interpretacją profili.
- `last_profile_issue_key` — dzień i kierunek ostatniego problematycznego profilu.
- `last_history_request` — ostatnie zapytanie archiwum: dzień, profil/rejestr
  (`profile`/`readings`) oraz pobór/oddanie (`consum`/`oze`).
- `last_api_error_request` i `last_api_response_summary` — kontekst ostatniej
  odrzuconej odpowiedzi JSON oraz jej struktura, bez treści pomiarów i komunikatów.
- `reading_issue_count`, `last_reading_issue_key`, `last_reading_issue` — problemy
  z dodatkowymi odczytami rejestrów; nie są one źródłem sum wirtualnego licznika.
- `last_successful_sync` — czas ostatniej udanej synchronizacji bieżących danych.
- `auto_clean_state_history` — czy włączono automatyczne czyszczenie historii stanów.
- `state_history_cleanup_last_requested` — czas ostatniego zlecenia czyszczenia
  Recorderowi; samo czyszczenie jest wykonywane asynchronicznie.
- `state_history_cleanup_error` — przyczyna pominięcia czyszczenia, np. brak
  potwierdzenia zapisu statystyk. Nie unieważnia udanej synchronizacji Taurona.

Jeśli `history_scan_next_day` się zmienia, import trwa. Jeśli nie zmienia się,
sprawdź ostatni błąd i czas ponowienia. Jeśli `downloaded_interval_count` wynosi
zero, a `profile_issue_count` rośnie, format odpowiedzi wymaga sprawdzenia;
samo czekanie na zakończenie skanowania nie rozwiąże tego problemu.

Tauron może zwrócić np. 23 wartości `null` i 24 etykiety godzin dla zwykłego dnia.
Od wersji 0.0.4 taka odpowiedź jest rozpoznawana jako brak odczytów,
bez ustalania rozdzielczości i bez wpisywania zer do statystyk. Zapisane wcześniej
odpowiedzi odrzucone z powodu daty albo rozdzielczości są ponownie przetwarzane
po restarcie. Rzeczywiście niejednoznaczne profile z niepustymi pomiarami nadal
pozostają oznaczone jako problem. Czas ostatniej próby jest aktualizowany także
na początku partii importu, a nie dopiero po jej zakończeniu.

Komunikat `Tauron API did not confirm a successful response` oznacza odrzuconą
odpowiedź API, a nie potwierdzony brak danych. Taka odpowiedź nie jest zamieniana
na zerowe zużycie. Odrzucony profil godzinowy zatrzymuje import na danym dniu.
Odrzucony dodatkowy rejestr (`readings`) jest zachowywany jako ostrzeżenie i nie
blokuje kolejnych dni, jeśli zapytania o profile doby już się powiodły.
Po aktualizacji usuwana jest stara przerwa po takim błędzie rejestru; postęp
i pobrane odpowiedzi pozostają zachowane. Limity Taurona i błędy połączenia
nadal mają swoje przerwy. Od wersji 0.0.3 odrzucona odpowiedź jest również
zachowywana w pliku
`/config/.storage/tauron_virtual_meter/tauron_virtual_meter.<entry_id>.last_api_error`.
Pole `data.response` w tym pliku pozwala ustalić przyczynę; nie przesyłaj całego
archiwum ani danych logowania. Dodatkowe zapytania o rejestry i same profile
godzinowe są rozróżniane w `last_api_error_request`.
Każda odrzucona odpowiedź jest też zachowywana pod kluczem danego zapytania
z końcówką `.error`, np. `tauron_virtual_meter.<entry_id>.2024-09-07.readings.oze.error`.
Nieudane historyczne odczyty rejestrów można ponowić akcją pełnego skanowania;
zwykłe odświeżanie sprawdza tylko ostatni tydzień.

Przykładowa karta Lovelace — zastąp identyfikator encji swoim:

```yaml
type: statistics-graph
title: Wirtualny licznik Tauron
entities:
  - sensor.twoja_encja_energia_pobrana
period: hour
stat_types:
  - state
days_to_show: 7
```

Dla wykresu energii zużytej w poszczególnych godzinach użyj `change` zamiast
`state`. Wykres zwykłej **Historii** nadal pokazuje chwile aktualizacji sensora,
a nie zaimportowane dawne zmiany stanu. Import nie zapisuje wstecz rekordów
`states` i nie modyfikuje bazy bezpośrednio.

Schodki w zwykłej Historii w godzinach instalacji mogą pochodzić z wcześniejszej
poprawki, która publikowała częściową sumę jako główny stan. To zapis przebiegu
importu, a nie rozkład zużycia. Nowy kod nie usuwa zapisanych już stanów.
Prawidłowy wykres godzinowy uzyskasz kartą statystyk powyżej (`state` dla stanu
licznika, `change` dla energii w każdej godzinie); ponowne pobieranie archiwum
nie jest potrzebne.

### Automatyczne czyszczenie historii stanów

Od wersji 0.0.6 opcja **Automatycznie czyść historię stanów liczników
po zapisie statystyk** może usunąć ślady pierwszego importu i zapobiegać mieszaniu
opóźnionych odczytów z czasem ich pobrania. Włącz ją w opcjach integracji.
Domyślnie jest wyłączona: usuwa całą zwykłą historię zmian stanu wyłącznie
liczników poboru i oddania tego wpisu integracji. Statystyki godzinowe i pliki
archiwum pozostają zachowane. Po włączeniu wykonuje się po zakończonym imporcie,
przy uruchomieniu już zsynchronizowanej integracji i po kolejnych synchronizacjach.

Integracja czeka na przetworzenie kolejki Recorder i sprawdza datę, stan oraz
sumę ostatniej zapisanej statystyki dla swoich sensorów. Dopiero po zgodnym
odczycie zwrotnym wywołuje standardową akcję `recorder.purge_entities` z listą
konkretnych identyfikatorów i `keep_days: 0`. Brak potwierdzenia lub błąd bazy
powoduje pominięcie czyszczenia. Kod nie usuwa statystyk i nie wykonuje własnego
SQL usuwającego dane. Przy starcie HA czeka z czyszczeniem do zakończenia startu.

### Dane opublikowane z opóźnieniem

Jeśli dziś o 16:10 eLicznik nie ma jeszcze dzisiejszych odczytów, integracja
zachowuje ostatnią znaną wartość; nie szacuje energii za brakujące godziny.
Kiedy pomiary pojawią się jutro, ponowne pobranie ostatniego tygodnia uzupełni
statystyki pod godzinami dzisiejszego pomiaru. Ponowne pobranie tych samych
wartości ich nie dubluje; korekty powodują ponowne przeliczenie sum.

Bez wykluczenia w Recorderze zwykła Historia rejestruje nowy stan dopiero w chwili
pobrania i może połączyć te stany z zaimportowanymi statystykami. Wymagane
wykluczenie zapobiega dopisywaniu kolejnych takich stanów; opcjonalne czyszczenie
usuwa dawne ślady importu. Karta `statistics-graph` z okresem `hour` czyta
zaimportowane statystyki. Dla tych sensorów nie ma automatycznie tworzonych
statystyk pięciominutowych.

Jeśli usunąłeś już statystyki długoterminowe w Narzędziach deweloperskich,
przeładuj integrację po poprawieniu konfiguracji. Odtworzy historię godzinową
z lokalnego archiwum po zakończeniu skanowania, bez ponownego pobierania wszystkich
dawnych dni. Akcja `recorder.purge_entities` usuwa historię stanów; przycisk
usuwania statystyk długoterminowych usuwa inny zbiór danych.

### Diagnostyka cyklicznej synchronizacji

Od wersji 0.0.7 dostępne są dodatkowe atrybuty:

- `last_sync_attempt`, `last_sync_error` — czas ostatniej próby i błąd całej
  synchronizacji, niezależnie od zakończonego już importu historii.
- `last_sync_request` — ostatnio wykonywane zapytanie bieżącej synchronizacji.
- `sync_issue_count`, `last_sync_issue_request`, `last_sync_issue` — liczba i opis
  nieudanych zapytań w ostatniej próbie. Dodatkowe zestawienia mogą być niedostępne
  mimo poprawnego pobrania godzinowych pomiarów.

`last_successful_sync` oznacza zakończone odświeżenie, które przyjęło przynajmniej
jeden profil dobowy; nie oznacza, że Tauron opublikował dane za wszystkie godziny.
Aktualność samych pomiarów pokazuje `last_measurement_end`. Przy stanie
`unavailable` sprawdź także Ustawienia → System → Dzienniki oraz kartę integracji:
nieudany pierwszy odczyt po restarcie może uniemożliwić uruchomienie sensorów
wraz z ich atrybutami diagnostycznymi.

### Limit logowań Taurona

Komunikat `Tauron login limit: retry later` oznacza, że odpowiedź Taurona zawiera
informację o przekroczeniu liczby logowań. Nie oznacza błędnego hasła. Nie usuwaj
integracji ani archiwum. W wersji 0.0.7 ponowne próby uruchomienia wpisu i
synchronizacja bieżąca nie respektowały przerwy zapisanej dla importu historii.
Na czas blokady można wyłączyć wpis integracji w Ustawienia → Urządzenia i usługi,
żeby zatrzymać automatyczne próby, a później ponownie go włączyć.

Od wersji 0.0.8 integracja zapisuje wspólny termin `api_retry_after` dla
uruchomienia, synchronizacji i importu historii. Przed tym terminem nie wysyła
zapytań do Taurona, również po restarcie HA. Przerwa wynosi co najmniej godzinę
lub dłuższe `Retry-After`, jeśli Tauron je poda. Bez takiego nagłówka godzina jest
lokalnym odstępem ponowienia, a nie gwarancją odblokowania konta przez Tauron.
W czasie przerwy karta nieudanego uruchomienia pokazuje termin następnej
najwcześniejszej próby w strefie Europe/Warsaw. Faktyczna próba może nastąpić
później, zgodnie z harmonogramem HA.

## Synchronizacja i pełny dostępny okres

Od wersji 0.0.5 dostępne jest domyślnie włączone **automatyczne
wykrywanie dostępności historii**. Integracja sprawdza pełne zestawienie miesięczne
poboru i oddania. Jeśli oba mają rozpoznawalny format i wyłącznie puste wartości
`null`, omija pozostałe dni tego miesiąca i sprawdza miesiąc wcześniejszy. Nie
kończy wyszukiwania na pierwszej przerwie, więc nadal może znaleźć starsze dane.
W miesiącach z pomiarami pobierane są profile dobowe; na ich podstawie ustalana
jest najstarsza dostępna godzina, osobno dla poboru i oddania.

Zero kWh oznacza dostępny pomiar i nie powoduje pominięcia miesiąca. Samo `sum: 0`
nie wystarcza. Błąd API, nieznany format, sprzeczne pola, znane już pomiary dobowe
albo nierozwiązany błąd profilu powodują powrót do skanowania dobowego. Ostatni
tydzień oraz bieżący miesiąc nie są pomijane tą metodą. Wyniki zestawień są
przechowywane przez dobę i zapisywane w archiwum jako `availability.RRRR-MM.*`.

To rozpoznawanie danych udostępnianych przez eLicznik w wybranym zakresie,
nie ustalanie daty fizycznego montażu licznika. Zgodność odpowiedzi miesięcznych
z profilem dobowym wymaga potwierdzenia na rzeczywistym koncie; nieznany format
nie uruchamia optymalizacji. Jeśli zestawienia miesięczne nie są wiarygodne dla
Twojego konta, wyłącz opcję w ustawieniach integracji. Pominięty zakres zostanie
wtedy ponownie otwarty do sprawdzania dzień po dniu, z zachowaniem pobranych danych.
Akcja pełnego skanowania również czyści pamięć wyników wykrywania.

Pominięty miesiąc zachowuje odpowiedzi miesięczne i zakres pominięcia; nie tworzy
sztucznych odczytów zerowych i nie pobiera osobnych profili ani rejestrów za każdy
z tych dni. Licznik `empty_profile_day_count` dotyczy wyłącznie pobranych profili
dobowych, a `history_skipped_day_count` dni pominiętych na podstawie zestawień.

- Domyślnie aktualizacja co 60 minut. Ponownie pobierany jest bieżący dzień
  i siedem poprzednich dni: pozwala uzupełniać opóźnione dane i korekty.
- Domyślnie zakres od **2000-01-01**: szerokie wyszukiwanie bez zatrzymywania
  się na pustych dniach. To dolna granica przeszukiwania, a nie wykryta data
  pierwszego pomiaru. Nie ma potwierdzonego endpointu zwracającego najstarszą datę.
- Archiwum przetwarza do 14 kroków na minutę, chronologicznie wstecz; krok to
  jedna doba albo pominięcie pustej części miesiąca. Duży zakres może
  wymagać wielu godzin, a przy ograniczeniach Taurona — dłużej. Każdy dzień ma
  osobny zapis postępu. Po restarcie pobieranie jest kontynuowane.
- Zakres oznacza wszystkie sprawdzone dni, również dni bez danych. Nie jest
  gwarancją, że Tauron udostępnia całą historię od założenia konta.
- Po skanowaniu ponownie przeliczana jest cała oś statystyk. Ponowny import
  tych samych godzin aktualizuje istniejące wartości, bez dopisywania zużycia.
- Starsze korekty poza ostatnim tygodniem wymagają ponownego skanowania.
  Akcja `rescan_history` wznawia skan całego skonfigurowanego okresu.
- Usunięty chwilowo odczyt nie jest zamieniany na zero. Wcześniejsza obserwacja
  pozostaje w archiwum i zwiększa licznik problemów do sprawdzenia.

Ustaw `interval_minutes: 0`, aby bieżące odświeżanie uruchamiać według własnego
planu przez akcję `tauron_virtual_meter.sync`. Import początkowy nadal działa w tle.
Przykład automatyzacji po wybraniu prawidłowego `entry_id`:

```yaml
alias: Tauron — synchronizacja co godzinę
triggers:
  - trigger: time_pattern
    minutes: "15"
actions:
  - action: tauron_virtual_meter.sync
    data:
      entry_id: TWOJ_IDENTYFIKATOR_WPISU_INTEGRACJI
mode: single
```

Akcję można też wywołać w Narzędziach deweloperskich, wybierając wpis integracji.
Brak połączenia nie zeruje danych. Błąd logowania uruchamia ponowną autoryzację.
Po chwilowym zerwaniu połączenia, przekroczeniu czasu odpowiedzi albo błędzie
serwera HTTP 5xx import czeka kolejno 1, 2, 4, 8 i maksymalnie 15 minut.
Po pomyślnym przetworzeniu całego dnia licznik takich awarii jest zerowany.
Próba następuje na najbliższym wolnym wywołaniu minutowego harmonogramu po
`history_retry_after`; trwająca synchronizacja bieżąca może ją opóźnić.

HTTP 429 lub komunikat Taurona o zbyt wielu logowaniach nadal oznacza co najmniej
godzinę przerwy; dłuższe `Retry-After` zwrócone przez serwer jest respektowane.
Pozostałe błędy API również zachowują godzinną przerwę. Ustalony czas ponowienia
jest przywracany po restarcie. Starsza godzinna przerwa bez zapisanego typu błędu
nie jest przenoszona przy pierwszej aktualizacji do tej poprawki.

Udane zapytania z aktualnie przetwarzanego dnia są zapamiętywane. Po błędzie
ponawiane są brakujące zapytania, z wykorzystaniem zapisanych już odpowiedzi.
Zwykła synchronizacja ostatniego tygodnia i celowe ponowne skanowanie zakończonych
dni nadal pobierają świeże dane, aby wykrywać korekty.

## Zachowane dane i dokładność

W `/config/.storage/tauron_virtual_meter/` zapisywane są oryginalne odpowiedzi
profili dobowych dla poboru i oddania oraz odczyty rejestrów dla każdego dnia.
Obejmuje to pola taryf, stref, statusów oraz inne pola zwracane przez te endpointy.
Zachowywana jest też lista liczników i ostatnie odpowiedzi zestawień miesiąca/roku.
Nieznane pola nie są usuwane. Kolejne pobranie zastępuje surową odpowiedź danego
dnia; nie jest to archiwum każdej wersji odpowiedzi. Pliki mogą zawierać dane
prywatne — uwzględnij je w swoich kopiach zapasowych.

Po aktualizacji i restarcie integracja automatycznie przenosi swoje dotychczasowe
pliki z `/config/.storage/tauron_virtual_meter.*` do tego podkatalogu. Nazwy plików
pozostają bez zmian: np. `tauron_virtual_meter.<entry_id>.index`. Zachowane są
odczyty, postęp skanowania, terminy ponawiania i częściowo przetwarzany dzień.
Nie przenoś plików ręcznie i nie uruchamiaj pełnego skanowania od początku.
Migracja obejmuje pliki danego wpisu integracji i wznawia się po przerwaniu.
Jeśli istnieją już różne pliki pod tą samą nazwą, aktywny plik w nowym katalogu
pozostaje, a starszy trafia do podkatalogu `legacy/` do sprawdzenia.

„Wszystkie dane” dotyczy znanych endpointów pomiarowych **eLicznik** dla wybranego
licznika. Nie obejmuje faktur, umów, płatności ani nieodkrytych endpointów Mój Tauron.
Nie pobiera historycznych zestawień miesiąc/rok: zachowuje ich dokładniejsze
profile dobowe i ostatnie zestawienia kontrolne.

Wersja 0.0.5 importuje **profile godzinowe** zgodnie z numeracją `Hour` od 1
znaną z integracji źródłowej. Godziny przeliczane są z Europe/Warsaw na UTC.
Każde zapytanie o profil dotyczy jednego dnia (`from == to`); używana jest data
tego zapytania, tak jak w Tauron AMIplus. Pole `Date` poszczególnych wierszy
nie jest podstawą odrzucenia całej doby i pozostaje bez zmian w surowym archiwum.
Obsługuje 23 i 25 godzin w dniach zmiany czasu, jeśli odpowiedź jednoznacznie
rozróżnia pomiary. Niejednoznaczne 24 próbki w takiej dobie, profil kwartalny,
nieznany format i nieprawidłowe wartości pozostają w oryginalnym archiwum;
nie są przeliczane przez zgadywanie. Licznik `profile_issue_count` sygnalizuje
problem. Bez rzeczywistej próbki nie można potwierdzić, czy Twój licznik
udostępnia drobniejszą rozdzielczość niż godzina.

Braki w pomiarach oznaczają braki w sumie znanych danych, nie zerowe zużycie.
Nie odtwarzamy dokładnego przyrostu w brakujących godzinach z miesięcznych sum.
To opóźniony licznik energii z sieci — nie pomiar chwilowej mocy w W ani całości
zużycia domu z fotowoltaiką. Dostępność i częstotliwość publikacji zależą od Taurona.

## Źródła i licencja

Logowanie i endpointy na podstawie
[Tauron AMIplus — Piotr Machowski](https://github.com/PiotrMachowski/Home-Assistant-custom-components-Tauron-AMIplus),
commit `eff7c51b473af0300be8e4ae8087310b563d3bbf`, licencja MIT w pliku `LICENSE`.
Import statystyk oparty na oficjalnym
[interfejsie Recorder Home Assistant](https://github.com/home-assistant/core/blob/dev/homeassistant/components/recorder/statistics.py).
Ta integracja ma odrębną domenę i może być zainstalowana obok Tauron AMIplus.
