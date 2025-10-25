# Came Connect

Integrazione Home Assistant per impianti domotici CAME ETI/Domo, versione ottimizzata.

Basata sul lavoro originale di [Den901](https://github.com/Den901/ha_came).

## Modifiche rispetto all'integrazione originale

- Risolto problema che bloccava Home Assistant durante la disinstallazione
- Corretta procedura di disinstallazione con timeout
- Semplificati ID univoci: `{platform}.{nome_dispositivo}_{act_id}` (es: `light.cucina_59`)
- Configurazione solo tramite UI (rimosso supporto YAML)
- Rimossa dipendenza dal token di autenticazione
- Energy sensor ora mantengono i valori dopo il riavvio di Home Assistant

**Nota importante:** La migrazione degli ID dispositivo deve essere effettuata manualmente. I dispositivi avranno nuovi ID univoci basati sui nomi originali CAME.

## Installazione

### Installazione tramite HACS

1. Apri HACS in Home Assistant
2. Clicca su "Integrazioni"
3. Clicca sul menu in alto a destra → "Archivi personalizzati"
4. Aggiungi l'URL: `https://github.com/StefanoPaoletti/Came_Connect`
5. Seleziona categoria: "Integration"
6. Clicca "Aggiungi"
7. Cerca "Came Connect" e clicca "Scarica"
8. Riavvia Home Assistant

### Configurazione

1. Vai su Impostazioni → Dispositivi e servizi
2. Clicca "+ Aggiungi integrazione"
3. Cerca "Came Connect"
4. Inserisci l'indirizzo IP del tuo ETI/Domo
5. Completa la configurazione

## Migrazione dall'integrazione originale (Den901)

Se hai già installato l'integrazione di Den901 e non riesci a disinstallare, segui questi passaggi:

### 1. Installa Came Connect

- Aggiungi il repository a HACS come descritto sopra
- Installa "Came Connect"
- Riavvia Home Assistant

### 2. Rimuovi l'integrazione Den901

- Vai su Impostazioni → Dispositivi e servizi
- Trova "CAME ETI/Domo" (Den901)
- Clicca sui tre puntini → Elimina

### 3. Rimuovi il repository Den901 da HACS

- Apri HACS → Integrazioni
- Cerca "CAME ETI/Domo"
- Clicca sui tre puntini → Rimuovi

### 4. Pulisci configuration.yaml

Rimuovi la configurazione YAML se presente:
```yaml
came:
  host: ...
  username: ...
  password: ...
  token: ...
```

Riavvia Home Assistant.

### 5. Configura Came Connect

- Vai su Impostazioni → Dispositivi e servizi
- Clicca "+ Aggiungi integrazione"
- Cerca "Came Connect"
- Inserisci l'indirizzo IP del tuo ETI/Domo

## Dispositivi supportati e testati

L'integrazione è stata testata con successo con i seguenti dispositivi:

- Luci on/off
- Termostati (climatizzazione e riscaldamento)
- Relè generici (switch)
- Energy sensor (monitoraggio consumi)
- Digital input (sensori binari)

## Servizi disponibili

L'integrazione espone i seguenti servizi per automazioni avanzate:

`came.force_update` - Forza l'aggiornamento immediato dello stato di tutti i dispositivi.
```yaml
service: came.force_update
```

`came.pull_devices` - Rileva e aggiunge automaticamente nuovi dispositivi dall'ETI/Domo.
```yaml
service: came.pull_devices
```

`came.refresh_scenarios` - Aggiorna l'elenco degli scenari disponibili.
```yaml
service: came.refresh_scenarios
```

## Debug

Per abilitare i log di debug, aggiungi al file `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.came: debug
```

Riavvia Home Assistant per applicare le modifiche.

I log saranno disponibili in Impostazioni → Sistema → Log o nel file `/config/home-assistant.log`.

## Supporto

Per segnalare problemi o richiedere nuove funzionalità, apri una issue su GitHub: https://github.com/StefanoPaoletti/Came_Connect/issues

## Licenza

MIT License - vedi file LICENSE per dettagli.
