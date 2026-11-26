# Historia zmian

## 0.0.6 — 2026-11-26

- Naprawiono zgodność importowanych statystyk z kontrolą klasy stanu HA:
  po wykluczeniu sensorów w Recorderze integracja deklaruje `state_class: total`.
  Bez wykluczenia zachowuje brak klasy, ostrzega w logu i udostępnia atrybut
  `recorder_exclusion_required`; nie uruchamia błędnego naliczania opóźnionych danych.
- Udokumentowano wymagane wykluczenie w `configuration.yaml` oraz przywracanie
  statystyk z archiwum. Nie usuwać statystyk w odpowiedzi na ostrzeżenie HA.
- Dodano domyślnie wyłączoną opcję automatycznego czyszczenia zwykłej historii
  stanów liczników po imporcie i każdej synchronizacji. Statystyki i archiwum
  pozostają zachowane; czyszczenie wymaga potwierdzenia zapisu ostatniej statystyki.
- Dodano atrybuty statusu czyszczenia i opis zachowania dla opóźnionych odczytów.
- Weryfikacja: 88 testów lokalnych, w tym kontrola zakresu czyszczenia, brak
  kasowania przy błędzie bazy i import opóźnionych pomiarów bez podwójnego naliczania.

## 0.0.5 — 2026-11-26

- Dodano automatyczne sprawdzanie dostępności danych w zestawieniach miesięcznych
  poboru i oddania, z pomijaniem rozpoznanych pustych miesięcy. Wyszukiwanie nie
  kończy się na pierwszym pustym miesiącu i nie traktuje zera jako braku odczytu.
- Nieznany format lub sprzeczność z profilem dobowym pozostawia skanowanie dobowe.
  Opcję można wyłączyć; wcześniej pominięty zakres zostanie sprawdzony ponownie.
- Dodano najstarszy znaleziony pomiar i liczniki pominiętych miesięcy/dni w atrybutach.
- Weryfikacja: 77 testów lokalnych. Brak testu nowych zapytań miesięcznych na
  rzeczywistym koncie Taurona; nieznany format odpowiedzi oznacza zwykły skan dobowy.

## 0.0.4 — 2026-11-26

- Puste profile (np. 23 wartości `null` i 24 etykiety godzin) są rozpoznawane
  jako brak pomiarów, bez błędu rozdzielczości i bez tworzenia zerowych odczytów.
- Po restarcie zapisane profile odrzucone z powodu rozdzielczości są przeliczane
  ponownie. Dodano atrybut `empty_profile_day_count`.
- Usunięta stara przerwa po błędzie rejestru nie pozostawia już nieaktualnego
  `last_history_error`. Początek próby importu jest od razu widoczny w atrybutach.
- Weryfikacja: 59 testów lokalnych, w tym profil odtworzony ze zgłoszonej odpowiedzi.

## 0.0.3 — 2026-11-26

- Odrzucenie dodatkowego odczytu rejestru nie blokuje już pobierania profili
  kolejnych dni. Odpowiedź jest archiwizowana, a brak rejestru sygnalizują
  atrybuty `reading_issue_count` i `last_reading_issue_key`.
- Aktualizacja wznawia import przerwany w 0.0.2 po odrzuceniu rejestru, bez
  utraty pobranych profili. Odrzucenia samych profili i limity nadal blokują import.
- Odrzucone odpowiedzi API są zachowywane lokalnie w pliku `last_api_error`,
  z informacją o dniu, kierunku i rodzaju zapytania. Nie są uznawane za brak danych.
- Dodano atrybuty `last_history_request`, `last_api_error_request`,
  `last_api_response_summary` i `last_profile_issue_key` do diagnozowania
  przerw importu i niejednoznacznych profili.

Weryfikacja: 55 testów lokalnych, w tym kontynuacja importu po odrzuceniu
rejestru, zachowanie blokady dla odrzuconych profili oraz archiwizacja błędów.
Brak automatycznego testu uruchomieniowego w działającym Home Assistant.

## 0.0.2 — 2026-11-26

- Pliki integracji są przechowywane w `/config/.storage/tauron_virtual_meter/`.
  Przy starcie dotychczasowe archiwum jest automatycznie przenoszone, z zachowaniem
  pomiarów i postępu. Migracja jest wznawialna; konflikty są zachowywane w `legacy/`.
- Chwilowe błędy połączenia i HTTP 5xx mają ponowienia po 1, 2, 4, 8 i maksymalnie
  15 minutach zamiast stałej godziny. Wyraźne limity Taurona nadal wymagają
  dłuższej przerwy; HTTP `Retry-After` jest respektowane.
- Import wznawia przerwany dzień od brakujących zapytań, wykorzystując zapisane
  już odpowiedzi. Dodano atrybut `history_retry_kind` i zachowanie przerwy po restarcie.
- Częściowa suma podczas importu jest teraz atrybutem `downloaded_energy_kwh`.
  Główny licznik nie rośnie już wskutek dopisywania kolejnych miesięcy archiwum,
  co wcześniej tworzyło mylące schodki w zwykłej Historii.
- Dodano ikonę licznika z akcentami magenta do dokumentacji i katalogu
  `brand/` integracji (256 px oraz 512 px; przezroczyste tło).
- Usunięto błędne odrzucanie profili dobowych z komunikatem
  `Response contains a different date`. Pomiary są przypisywane do dnia
  wskazanego w zapytaniu, zgodnie z zachowaniem Tauron AMIplus.
- Po restarcie automatycznie przeliczane są zapisane profile odrzucone przez
  tę kontrolę daty; bez ponownego pobierania i bez zerowania postępu.
- Sensory udostępniają częściową sumę dostępnych pomiarów w atrybutach,
  bez czekania na zakończenie skanowania całego okresu.
- Atrybuty encji pokazują liczbę pobranych godzin, pozostałych dni oraz ostatni
  błąd importu i termin ponowienia.
- Dane częściowe nie trafiają do końcowej historii statystyk, dopóki nie zostanie
  ustalony początek licznika po zakończeniu skanowania.
- Dodano testy publikowania częściowych danych i diagnostyki błędów.

Weryfikacja: 47 testów lokalnych, w tym testy migracji na rzeczywistych plikach
w katalogach tymczasowych i testy ponawiania z atrapami Home Assistant/aiohttp.
Brak automatycznego testu uruchomieniowego w działającym Home Assistant.

## 0.0.1 — 2026-11-26

Pierwsza wersja testowa integracji Home Assistant.

- Wirtualne liczniki poboru i oddania energii w kWh.
- Import godzinowych statystyk bezpośrednio pod identyfikatory encji.
- Synchronizacja okresowa, ręczna lub przez automatyzację.
- Wznawialne przeszukiwanie archiwum, domyślnie od 2000-01-01.
- Archiwizacja oryginalnych odpowiedzi znanych endpointów pomiarowych eLicznik.
- Ponowne sprawdzanie ostatniego tygodnia i możliwość pełnego ponownego skanowania.
- Obsługa jednoznacznych profili 23/25-godzinnych przy zmianie czasu.

Weryfikacja: 19 testów lokalnych z użyciem atrap Home Assistant/aiohttp;
kontrola składni Python i plików JSON. Brak testu w działającym Home Assistant
oraz na rzeczywistym koncie eLicznik. Nieznane formaty i profile kwartalne
są archiwizowane bez automatycznego przeliczania.
