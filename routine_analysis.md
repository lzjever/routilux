# Routine Analysis: analyzer_demo_routines.py

**Source File:** `/home/percy/works/mygithub/routilux/examples/analyzer_demo_routines.py`

Found **6** routine(s) in this file.

---

## 1. DataCollector

Collects data from multiple sources and aggregates them.

This routine demonstrates:
- Trigger slot for entry point
- Multiple output events
- Configuration parameters

**Line:** 12

### 📥 Input Slots

#### `trigger`

**Handler:** `_handle_trigger()` | **Merge Strategy:** `override`


### 📤 Output Events

#### `data`

**Output Parameters:** `collected_data`, `count`, `timestamp`

#### `error`

**Output Parameters:** `error_message`, `error_code`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `collection_timeout` | `30` |
| `max_items` | `100` |
| `aggregation_mode` | `sum` |

### 🔧 Methods

#### `__init__(self)`

#### `_handle_trigger(self, source)`

Handle trigger and collect data.

**Emits Events:** `data`



---

## 2. DataProcessor

Processes data with configurable transformations.

This routine demonstrates:
- Input slot with handler
- Append merge strategy
- Multiple processing methods

**Line:** 51

### 📥 Input Slots

#### `input`

**Handler:** `process()` | **Merge Strategy:** `append`


### 📤 Output Events

#### `output`

**Output Parameters:** `processed_data`, `status`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `processing_mode` | `batch` |
| `batch_size` | `10` |
| `enable_validation` | `True` |

### 🔧 Methods

#### `__init__(self)`

#### `process(self, data)`

Process incoming data.

**Emits Events:** `output`



---

## 3. DataValidator

Validates data according to rules.

This routine demonstrates:
- Multiple input slots
- Conditional output events
- Custom validation logic

**Line:** 97

### 📥 Input Slots

#### `data`

**Handler:** `validate()` | **Merge Strategy:** `override`

#### `metadata`

**Handler:** `validate()` | **Merge Strategy:** `override`


### 📤 Output Events

#### `valid`

**Output Parameters:** `validated_data`, `score`

#### `invalid`

**Output Parameters:** `errors`, `data`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `validation_rules` | `[required, type_check]` |
| `strict_mode` | `True` |

### 🔧 Methods

#### `__init__(self)`

#### `validate(self, data)`

Validate incoming data.

**Emits Events:** `valid`, `invalid`



---

## 4. DataAggregator

Aggregates data from multiple sources.

This routine demonstrates:
- Custom merge strategy
- Multiple input sources
- Complex aggregation logic

**Line:** 138

### 📥 Input Slots

#### `input`

**Handler:** `aggregate()` | **Merge Strategy:** `None`


### 📤 Output Events

#### `result`

**Output Parameters:** `aggregated_value`, `sources_count`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `aggregation_function` | `mean` |
| `include_metadata` | `True` |

### 🔧 Methods

#### `__init__(self)`

#### `_custom_merge(self, old_data, new_data)`

Custom merge strategy for aggregation.

#### `aggregate(self, data)`

Aggregate incoming data.

**Emits Events:** `result`



---

## 5. DataRouter

Routes data based on conditions.

This routine demonstrates:
- Conditional routing
- Multiple output events for routing
- Decision logic

**Line:** 204

### 📥 Input Slots

#### `input`

**Handler:** `route()` | **Merge Strategy:** `override`


### 📤 Output Events

#### `high_priority`

**Output Parameters:** `data`, `priority`

#### `medium_priority`

**Output Parameters:** `data`, `priority`

#### `low_priority`

**Output Parameters:** `data`, `priority`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `routing_rules` | `{high: >10, medium: >5, low: <=5}` |
| `default_route` | `low` |

### 🔧 Methods

#### `__init__(self)`

#### `route(self, data)`

Route data based on priority.

**Emits Events:** `high_priority`, `medium_priority`, `low_priority`



---

## 6. DataSink

Final destination for processed data.

This routine demonstrates:
- Multiple input slots from different sources
- Data storage/saving
- Final output

**Line:** 246

### 📥 Input Slots

#### `high_input`

**Handler:** `save()` | **Merge Strategy:** `override`

#### `medium_input`

**Handler:** `save()` | **Merge Strategy:** `override`

#### `low_input`

**Handler:** `save()` | **Merge Strategy:** `override`


### 📤 Output Events

#### `completed`

**Output Parameters:** `saved_count`, `timestamp`


### ⚙️ Configuration

| Parameter | Value |
|-----------|-------|
| `output_format` | `json` |
| `save_to_file` | `False` |

### 🔧 Methods

#### `__init__(self)`

#### `save(self, data)`

Save incoming data.

**Emits Events:** `completed`

