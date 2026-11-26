# Historia zmian

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
