# Contributi

Questo repository è una versione ottimizzata dell'integrazione CAME originale di [Den901](https://github.com/Den901/ha_came), personalizzata per specifiche esigenze.

## Policy sui contributi

Questo progetto **non accetta pull request o contributi esterni**. Il codice è condiviso pubblicamente per trasparenza e come riferimento.

## Modifiche apportate

Le principali modifiche rispetto all'integrazione originale includono:

- Risolto problema che bloccava Home Assistant durante la disinstallazione
- Corretta procedura di disinstallazione con timeout
- Semplificati ID univoci basati sui nomi originali CAME
- Configurazione solo tramite UI (rimosso supporto YAML)
- Rimossa dipendenza dal token di autenticazione
- Energy sensor ora mantengono i valori dopo il riavvio di Home Assistant

## Segnalazione problemi

Per segnalare bug o problemi specifici di questa versione, è possibile aprire una issue su questo repository:
https://github.com/StefanoPaoletti/Came_Connect/issues

## Contribuire al progetto originale

Per contribuire al progetto originale o segnalare problemi generali dell'integrazione CAME, fare riferimento al repository originale:
https://github.com/Den901/ha_came

## Licenza

Questo progetto è rilasciato sotto licenza MIT, come il progetto originale.
