# Came Connect

Integrazione Home Assistant per impianti domotici CAME ETI/Domo, versione ottimizzata.

Basata sul lavoro originale di [Den901](https://github.com/Den901/ha_came).

## Modifiche rispetto all'integrazione originale

- Risolto problema che bloccava Home Assistant durante la disinstallazione
- Corretta procedura di disinstallazione con timeout
- Semplificati ID univoci basati sui nomi originali CAME
- Configurazione solo tramite UI (rimosso supporto YAML)
- Rimossa dipendenza dal token di autenticazione
- Energy sensor ora mantengono i valori dopo il riavvio di Home Assistant

**Nota:** La migrazione degli ID dispositivo deve essere effettuata manualmente.

## Piattaforme supportate

| Piattaforma | Descrizione |
|-------------|-------------|
| `light` | Luci on/off, dimmer e RGB |
| `climate` | Termostati e zone termiche |
| `cover` | Tapparelle e coperture motorizzate |
| `switch` | Relè generici |
| `sensor` | Sensori analogici e contatori energia |
| `binary_sensor` | Ingressi digitali |
| `scene` | Scenari CAME |

## Installazione

### Tramite HACS

1. Apri HACS → Integrazioni
2. Clicca sul menu (tre puntini) → Archivi personalizzati
3. Aggiungi URL: `https://github.com/StefanoPaoletti/Came_Connect`
4. Categoria: Integration
5. Cerca "Came Connect" e clicca "Scarica"
6. Riavvia Home Assistant

### Configurazione

1. Vai su Impostazioni → Dispositivi e servizi
2. Clicca "+ Aggiungi integrazione"
3. Cerca "Came Connect"
4. Inserisci l'indirizzo IP del tuo ETI/Domo

## Debug

Aggiungi al file `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.came: debug
```

Riavvia Home Assistant per applicare le modifiche.

## Supporto

Per segnalare problemi o richiedere nuove funzionalità:
https://github.com/StefanoPaoletti/Came_Connect/issues

## Licenza

MIT License - vedi [LICENSE](https://github.com/StefanoPaoletti/Came_Connect/blob/main/LICENSE) per dettagli.
