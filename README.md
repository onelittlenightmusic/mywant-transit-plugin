# mywant-transit-plugin

MyWant custom type plugin for transit route search via Yahoo!路線情報.

## Installation

```bash
cd ~/.mywant/custom-types
git clone https://github.com/onelittlenightmusic/mywant-transit-plugin
```

## Usage

```yaml
metadata:
  name: shinjuku_to_shibuya
  type: transit_search
spec:
  params:
    from: 新宿
    to: 渋谷
```

## Requirements

- Python 3, Playwright, Chrome with remote debugging
