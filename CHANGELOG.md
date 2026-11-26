# Historia zmian

## Poprawki na main po 0.0.1 (bez zmiany wersji)

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
