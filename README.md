# Tauron Virtual Meter — wersja 0.0.3

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

**Aktualizacja do 0.0.3:** zainstaluj nowe wydanie i uruchom ponownie Home Assistant.
Archiwum zostanie automatycznie przeniesione do `/config/.storage/tauron_virtual_meter/`,
z zachowaniem pomiarów oraz postępu importu. Zapisane profile odrzucone przez
wcześniejszą kontrolę daty zostaną ponownie przeliczone. Nie usuwaj wpisu integracji,
nie przenoś plików ręcznie i nie uruchamiaj skanowania od początku.
Wersja 0.0.3 wznawia też import zatrzymany na dodatkowym odczycie rejestru;
odrzucone rejestry są widoczne jako ostrzeżenia i nie blokują pobierania profili.
Szczegóły zmian znajdują się w [historii zmian](CHANGELOG.md).

[![Dodaj repozytorium do Home Assistant przez HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=direk&repository=tauron-virtual-meter&category=integration)

Kliknij przycisk, wybierz swój Home Assistant i potwierdź dodanie repozytorium
w HACS. Następnie zainstaluj integrację i uruchom ponownie Home Assistant.
Przycisk wymaga skonfigurowanego HACS.

Paczka instalacyjna: [wydanie 0.0.3](https://github.com/direk/tauron-virtual-meter/releases/tag/v0.0.3).
Rozpakuj plik `tauron_virtual_meter-0.0.3.zip`, a następnie:

1. Skopiuj katalog `custom_components/tauron_virtual_meter` do
   `/config/custom_components/tauron_virtual_meter` na urządzeniu z Home Assistant.
2. Uruchom ponownie Home Assistant.
3. W Ustawienia → Urządzenia i usługi → Dodaj integrację wybierz **Tauron Virtual Meter**.
4. Zaloguj się kontem **eLicznik**, wybierz licznik oraz zakres przeszukiwania.
   Dla kolejnych liczników dodaj osobne wpisy integracji.

Wymagany jest współczesny Home Assistant z `recorder`, interfejsem
`async_import_statistics` oraz metadanymi `mean_type`/`unit_class`.
Minimalna obsługiwana wersja HA nie została jeszcze ustalona testem uruchomieniowym.

Możesz też dodać `https://github.com/direk/tauron-virtual-meter` do HACS
jako repozytorium niestandardowe typu **Integracja** i zainstalować stamtąd.
Instalacja przez HACS nie była jeszcze sprawdzana w działającym HA.

## Ikona integracji

Ikona licznika jest dołączona do katalogu `brand/` integracji w rozmiarach
256 × 256 i 512 × 512 px, z przezroczystym tłem. Home Assistant od wersji
2026.3 obsługuje takie [lokalne ikony integracji](https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/).
Po skopiowaniu aktualnego katalogu integracji uruchom ponownie Home Assistant
i odśwież stronę w przeglądarce.

## Historia tej samej encji

Integracja tworzy encje „Energia pobrana” i „Energia oddana”. Dokładne identyfikatory
znajdziesz w urządzeniu; HA nadaje je podczas instalacji.

Każda encja otrzymuje natywne statystyki godzinowe pod **własnym `entity_id`**.
Ich `state` to narastający wirtualny stan licznika, a `sum` to suma dostępnej energii.
Początek licznika to umowne zero przed pierwszym dostępnym pomiarem. Nie jest to
fizyczny stan rejestru na liczniku Taurona. Oryginalne rejestry są archiwizowane
oddzielnie, bez zgadywania godzin, do których się odnoszą.

Sensor celowo nie deklaruje `state_class`: automatyczne statystyki HA nie mogą
równolegle naliczać spóźnionych danych w momencie ich pobrania. Statystyki importuje
wyłącznie integracja, z datami pomiarów. Podczas skanowania pobrana suma jest
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
- `downloaded_energy_kwh` — suma dotychczas pobranych pomiarów; podczas importu
  może rosnąć wskutek dodawania starszych dni i nie oznacza bieżącego zużycia.
- `recovered_profile_count` — liczba zapisanych profili poboru/oddania odzyskanych
  po usunięciu błędnej kontroli pola daty (łącznie dla obu encji).
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

Jeśli `history_scan_next_day` się zmienia, import trwa. Jeśli nie zmienia się,
sprawdź ostatni błąd i czas ponowienia. Jeśli `downloaded_interval_count` wynosi
zero, a `profile_issue_count` rośnie, format odpowiedzi wymaga sprawdzenia;
samo czekanie na zakończenie skanowania nie rozwiąże tego problemu.

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

## Synchronizacja i pełny dostępny okres

- Domyślnie aktualizacja co 60 minut. Ponownie pobierany jest bieżący dzień
  i siedem poprzednich dni: pozwala uzupełniać opóźnione dane i korekty.
- Domyślnie zakres od **2000-01-01**: szerokie wyszukiwanie bez zatrzymywania
  się na pustych dniach. To dolna granica przeszukiwania, a nie wykryta data
  pierwszego pomiaru. Nie ma potwierdzonego endpointu zwracającego najstarszą datę.
- Archiwum skanuje po 14 dni na minutę, chronologicznie wstecz. Duży zakres może
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

Wersja 0.0.3 importuje **profile godzinowe** zgodnie z numeracją `Hour` od 1
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

## Testy

```sh
python3 -m unittest discover -s tests -v
```

Po instalacji należy sprawdzić dobę z eLicznik, sumy kWh, obie zmiany czasu,
przerwę w dostępie i restart HA. Testy lokalne nie zastępują tego sprawdzenia.

## Źródła i licencja

Logowanie i endpointy na podstawie
[Tauron AMIplus — Piotr Machowski](https://github.com/PiotrMachowski/Home-Assistant-custom-components-Tauron-AMIplus),
commit `eff7c51b473af0300be8e4ae8087310b563d3bbf`, licencja MIT w pliku `LICENSE`.
Import statystyk oparty na oficjalnym
[interfejsie Recorder Home Assistant](https://github.com/home-assistant/core/blob/dev/homeassistant/components/recorder/statistics.py).
Ta integracja ma odrębną domenę i może być zainstalowana obok Tauron AMIplus.
