# Telemetry-F1-2021

# Info

Currently the project is setup to obtain and insert only weather data from the PacketSessionData struct. Deserialization has kindly been done in CodeMasters by an anonymous poster and implemented as an open-source project by [chrishannam](https://github.com/chrishannam).

# Credits

Much of the code used in this repository is taken from [this repository](https://github.com/chrishannam/Telemetry-F1-2021) and [this CodeMasters thread!](https://forums.codemasters.com/topic/80231-f1-2021-udp-specification/?tab=comments#comment-624274)

Make sure to check the links and give them the credit that they deserved! I decided to reuse most of their code since it removes the complexity of handling packet encoding/decoding issues and lets me focus in the things I need to focus on, which is, to connect this to an Oracle Autonomous Database for data collection purposes.

# Installing

This references Chris' pip module, which you can use instead of the source code present in parts of this repository:
```bash
pip install Telemetry-F1-2021
```

# Simplest usage
```python
from telemetry_f1_2021.listener import TelemetryListener

listener = TelemetryListener(port=20777, host='localhost')
packet = listener.get()
```

