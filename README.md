# Tauron Virtual Meter — wersja 0.0.1

Niestandardowa integracja Home Assistant: wirtualny licznik energii pobranej
i oddanej, w kWh, z historią godzinową przypisaną bezpośrednio do encji.
Nie tworzy osobnego źródła `tauron_importer` i nie wymaga panelu Energia.

**Stan: prototyp do weryfikacji na koncie eLicznik.** Testy lokalne sprawdzają
przeliczanie profili i scenariusze importu. Nie wykonano logowania na rzeczywiste
konto ani testu w działającym Home Assistant. Nie pobrano jeszcze Twoich danych.
Transport oparto na aktualnym kodzie Tauron AMIplus, lecz odpowiedzi różnych
liczników i ograniczenia historyczne API trzeba sprawdzić w praktyce.

## Instalacja

[![Dodaj repozytorium do Home Assistant przez HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=direk&repository=tauron-virtual-meter&category=integration)

Kliknij przycisk, wybierz swój Home Assistant i potwierdź dodanie repozytorium
w HACS. Następnie zainstaluj integrację i uruchom ponownie Home Assistant.
Przycisk wymaga skonfigurowanego HACS.

Paczka instalacyjna: [wydanie 0.0.1](https://github.com/direk/tauron-virtual-meter/releases/tag/v0.0.1).
Rozpakuj plik `tauron_virtual_meter-0.0.1.zip`, a następnie:

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
wyłącznie integracja, z datami pomiarów. Po pierwszym pełnym skanowaniu publikuje
stan i całą historię. W trakcie skanowania stan pozostaje `unknown`; atrybut
`history_scan_next_day` pokazuje postęp. Puste odpowiedzi nie kończą wyszukiwania.

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
Brak połączenia nie zeruje danych. Błąd logowania uruchamia ponowną autoryzację;
błąd importu historycznego wstrzymuje kolejne próby na godzinę.

## Zachowane dane i dokładność

W `/config/.storage/tauron_virtual_meter.*` zapisywane są oryginalne odpowiedzi
profili dobowych dla poboru i oddania oraz odczyty rejestrów dla każdego dnia.
Obejmuje to pola taryf, stref, statusów oraz inne pola zwracane przez te endpointy.
Zachowywana jest też lista liczników i ostatnie odpowiedzi zestawień miesiąca/roku.
Nieznane pola nie są usuwane. Kolejne pobranie zastępuje surową odpowiedź danego
dnia; nie jest to archiwum każdej wersji odpowiedzi. Pliki mogą zawierać dane
prywatne — uwzględnij je w swoich kopiach zapasowych.

„Wszystkie dane” dotyczy znanych endpointów pomiarowych **eLicznik** dla wybranego
licznika. Nie obejmuje faktur, umów, płatności ani nieodkrytych endpointów Mój Tauron.
Nie pobiera historycznych zestawień miesiąc/rok: zachowuje ich dokładniejsze
profile dobowe i ostatnie zestawienia kontrolne.

Wersja 0.0.1 importuje **profile godzinowe** zgodnie z numeracją `Hour` od 1
znaną z integracji źródłowej. Godziny przeliczane są z Europe/Warsaw na UTC.
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
