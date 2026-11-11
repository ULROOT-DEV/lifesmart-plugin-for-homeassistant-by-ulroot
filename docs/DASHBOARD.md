# One product, several entities, one card

A protocol `idx` is a channel identifier. Home Assistant entities represent meaningful capabilities; dashboard cards are a separate presentation choice. For a CUBE, temperature, humidity and illuminance belong to one device and can share one card.

Open the device under **Settings → Devices & services → LifeSmart by ULROOT**, find its entity IDs, then add an **Entities** card using your actual IDs:

```yaml
type: entities
title: Living room CUBE
show_header_toggle: false
entities:
  - entity: sensor.living_room_cube_temperature
    name: Temperature
  - entity: sensor.living_room_cube_humidity
    name: Humidity
  - entity: sensor.living_room_cube_illuminance
    name: Illuminance
```

The IDs above are examples; Home Assistant generates names based on your devices and locale. This integration does not create or overwrite dashboards. Entity names follow your configured English/Korean language.

한국어: 장치 화면에서 실제 엔티티 ID를 확인하고 하나의 **엔티티 카드**에 온도·습도·조도를 추가하면 됩니다. `idx`마다 별도의 카드를 만들 필요는 없습니다. 위 ID는 예시이므로 실제 값으로 바꾸세요.
