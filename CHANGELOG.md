# Changelog

## 0.1.3

Neuer Schalter „Ein/Aus“ für die Cinebar. Er nutzt denselben Weg wie die Integration „Teufel Raumfeld“: Einschalten ruft am Raumfeld-Host `/leaveStandby` auf, Ausschalten `/enterManualStandby`. Der Betriebszustand wird alle 20 Sekunden abgefragt, nach dem Schalten sofort. „An“ bedeutet aktiv, Eco-Standby und manueller Standby zählen als „aus“, den genauen Zustand zeigt das Attribut `power_state`. Die Tests prüfen die Auswertung der Raumliste.

## 0.1.2

Die Abstände werden jetzt richtig mit Dezimalpunkt angezeigt, also 4,6 m statt 46 m für die Soundbar, 0,7 m statt 7 m für den Subwoofer und 2,0 m statt 20 m für die Rear-Lautsprecher. Die Umrechnung war vorhanden, wurde aber durch einen internen Namenskonflikt mit dem Wert-Property der Zahlenfelder von Home Assistant überschrieben. Außerdem ist die Zuordnung der Eingänge korrigiert: 0 ist Teufel Streaming, 1 ist Analog und 2 ist Optisch. TV (3) und HDMI (4) waren schon richtig. Ein neuer Test verhindert den Namenskonflikt künftig.

## 0.1.1

Weitere Eingänge und sinnvolle Einheiten für Lip Sync und Abstände. Zum Eingang kommen Analog, Optisch und Teufel Streaming hinzu. Lip Sync lässt sich jetzt in Millisekunden von 0 bis 100 in 1-ms-Schritten einstellen, und die Abstände von Soundbar, Subwoofer und Rear-Lautsprechern werden in Metern von 0,3 bis 12 angezeigt (intern in 0,1-m-Schritten). Die Zuordnung der neuen Eingänge zu den Zahlenwerten und die Skalen sind noch zu bestätigen.

## 0.1.0

Erste Version. Alle Einstellungen der Raumfeld-App für die Teufel Cinebar Lux als Home-Assistant-Entitäten, live über den WebSocket des Raumfeld-Hosts.
