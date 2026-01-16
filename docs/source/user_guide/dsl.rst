DSL (Domain Specific Language)
================================

The DSL (Domain Specific Language) module allows you to define workflows declaratively using YAML or JSON. This is useful for:

* **Workflow as Code**: Define workflows in configuration files
* **Dynamic Loading**: Load workflows from external sources
* **Version Control**: Track workflow definitions separately from code
* **No-Code/Low-Code**: Enable non-developers to create workflows

Basic Usage
------------

YAML Workflow Definition:

.. code-block:: yaml

   flow_id: "data_processing_pipeline"
   execution:
     strategy: "concurrent"
     timeout: 300.0
   routines:
     extractor:
       class: "myapp.routines.DataExtractor"
       config:
         source: "database"
         batch_size: 100
     validator:
       class: "myapp.routines.DataValidator"
       config:
         rules:
           - "data is not None"
           - "data.get('id') is not None"
     transformer:
       class: "myapp.routines.DataTransformer"
       config:
         transformations:
           - "normalize"
           - "validate"
     exporter:
       class: "myapp.routines.DataExporter"
       config:
         destination: "s3://my-bucket/data"
   connections:
     - from: "extractor.output"
       to: "validator.input"
     - from: "validator.valid"
       to: "transformer.input"
     - from: "transformer.output"
       to: "exporter.input"

Loading Workflow from YAML:

.. code-block:: python

   import yaml
   from routilux.dsl import load_flow_from_spec

   # Load YAML file
   with open("workflow.yaml") as f:
       spec = yaml.safe_load(f)

   # Create flow from spec
   flow = load_flow_from_spec(spec)

   # Execute
   job_state = flow.execute("extractor", entry_params={"data": "test"})

JSON Workflow Definition:

.. code-block:: json

   {
     "flow_id": "data_processing_pipeline",
     "execution": {
       "strategy": "concurrent",
       "timeout": 300.0
     },
     "routines": {
       "extractor": {
         "class": "myapp.routines.DataExtractor",
         "config": {
           "source": "database",
           "batch_size": 100
         }
       },
       "validator": {
         "class": "myapp.routines.DataValidator",
         "config": {
           "rules": [
             "data is not None",
             "data.get('id') is not None"
           ]
         }
       }
     },
     "connections": [
       {
         "from": "extractor.output",
         "to": "validator.input"
       }
     ]
   }

Loading Workflow from JSON:

.. code-block:: python

   import json
   from routilux.dsl import load_flow_from_spec

   # Load JSON file
   with open("workflow.json") as f:
       spec = json.load(f)

   # Create flow from spec
   flow = load_flow_from_spec(spec)

   # Execute
   job_state = flow.execute("extractor", entry_params={"data": "test"})

Spec Format
-----------

Flow Specification:

.. code-block:: python

   spec = {
       "flow_id": "my_flow",  # Optional: auto-generated if not provided
       "execution": {
           "strategy": "sequential" | "concurrent",  # Optional: "sequential" (default)
           "timeout": 300.0,  # Optional: default timeout in seconds
           "max_workers": 5  # Optional: for concurrent mode
       },
       "routines": {
           "routine_id": {  # Routine identifier
               "class": ClassName | "module.path.ClassName",  # Routine class
               "config": {  # Optional: configuration for routine
                   "key": "value"
               },
               "error_handler": {  # Optional: error handler configuration
                   "strategy": "stop" | "continue" | "retry" | "skip",
                   "max_retries": 3,
                   "retry_delay": 1.0,
                   "retry_backoff": 2.0,
                   "is_critical": false
               }
           }
       },
       "connections": [
           {
               "from": "source_routine.event_name",
               "to": "target_routine.slot_name",
               "param_mapping": {  # Optional: parameter mapping
                   "target_param": "source_param",
                   "other_param": "static_value"
               }
           }
       ]
   }

Routine Class Reference:

You can specify routine class in two ways:

1. **Direct Class Reference** (for in-memory specs):
   .. code-block:: python

      from myapp import routines

      spec = {
          "routines": {
              "processor": {
                  "class": routines.DataProcessor,  # Direct class reference
                  "config": {"threshold": 10}
              }
          }
      }

2. **Module Path String** (for loading from files):
   .. code-block:: yaml

      routines:
        processor:
          class: "myapp.routines.DataProcessor"  # Module path string
          config:
            threshold: 10

Error Handler Configuration:

.. code-block:: yaml

   routines:
     critical_task:
       class: "myapp.routines.CriticalTask"
       error_handler:
         strategy: "retry"  # or "stop", "continue", "skip"
         max_retries: 3
         retry_delay: 1.0
         retry_backoff: 2.0
         is_critical: true

   routines:
     optional_task:
       class: "myapp.routines.OptionalTask"
       error_handler:
         strategy: "continue"  # Continue on error
         is_critical: false

Parameter Mapping:

Map parameters when connecting events to slots:

.. code-block:: yaml

   connections:
     - from: "source.output"
       to: "target.input"
       param_mapping:
         input_data: "result"  # Map event.result to slot.input_data
         extra_param: "static_value"  # Pass static value

Connection Patterns:

.. code-block:: yaml

   # One-to-one
   connections:
     - from: "source.output"
       to: "target.input"

   # One-to-many (fan-out)
   connections:
     - from: "source.output"
       to: "processor1.input"
     - from: "source.output"
       to: "processor2.input"
     - from: "source.output"
       to: "processor3.input"

   # Many-to-one (fan-in)
   connections:
     - from: "source1.output"
       to: "aggregator.input"
     - from: "source2.output"
       to: "aggregator.input"
     - from: "source3.output"
       to: "aggregator.input"

Advanced Usage
-------------

Dynamic Workflow Loading:

.. code-block:: python

   import yaml
   import os
   from routilux.dsl import load_flow_from_spec

   # Load workflow from directory
   workflow_dir = "workflows"
   workflow_files = ["data_pipeline.yaml", "ml_pipeline.yaml"]

   flows = {}
   for filename in workflow_files:
       filepath = os.path.join(workflow_dir, filename)
       with open(filepath) as f:
           spec = yaml.safe_load(f)
           flow = load_flow_from_spec(spec)
           flows[flow.flow_id] = flow

   # Execute specific workflow
   job_state = flows["data_pipeline"].execute("extractor", entry_params={"data": "test"})

Workflow Validation:

.. code-block:: python

   from routilux.dsl import parse_spec

   # Parse spec without creating flow (for validation)
   spec = {
       "routines": {
           "processor": {"class": "myapp.routines.DataProcessor"}
       },
       "connections": []
   }

   parsed = parse_spec(spec)

   # Check for errors
   if not parsed.get("valid"):
       print(f"Validation errors: {parsed.get('errors', [])}")
   else:
       print("Workflow spec is valid!")

Environment-Specific Workflows:

.. code-block:: python

   import yaml
   import os
   from routilux.dsl import load_flow_from_spec

   # Load environment-specific config
   env = os.getenv("ENV", "development")
   config_file = f"workflow_{env}.yaml"

   with open(config_file) as f:
       spec = yaml.safe_load(f)

   flow = load_flow_from_spec(spec)

Exporting Workflows to DSL:

.. code-block:: python

   import json
   from routilux import Flow

   # Create flow programmatically
   flow = Flow(flow_id="my_workflow")
   # ... add routines and connections ...

   # Export to DSL spec
   spec = {
       "flow_id": flow.flow_id,
       "execution": {
           "strategy": flow.execution_strategy,
           "timeout": flow.execution_timeout
       },
       "routines": {},
       "connections": []
   }

   for routine_id, routine in flow.routines.items():
       spec["routines"][routine_id] = {
           "class": f"{routine.__class__.__module__}.{routine.__class__.__name__}",
           "config": routine._config
       }

   for conn in flow.connections:
       spec["connections"].append({
           "from": f"{conn.source_routine._id}.{conn.source_event.name}",
           "to": f"{conn.target_routine._id}.{conn.target_slot.name}",
           "param_mapping": conn.param_mapping or {}
       })

   # Save to file
   with open("workflow_export.json", "w") as f:
       json.dump(spec, f, indent=2)

Best Practices
--------------

1. **Version Control**: Store DSL files in version control alongside code

2. **Environment Separation**: Use different configs for dev/staging/prod

   .. code-block:: yaml

      # workflow_dev.yaml
      execution:
        strategy: "sequential"

      # workflow_prod.yaml
      execution:
        strategy: "concurrent"
        max_workers: 20

3. **Documentation**: Add comments to YAML files for clarity

   .. code-block:: yaml

      routines:
        # Extracts data from database
        extractor:
          class: "myapp.routines.DataExtractor"
          config:
            source: "database"  # Primary data source

4. **Validation**: Validate DSL specs before loading in production

   .. code-block:: python

      from routilux.dsl import parse_spec

      def load_workflow(spec_path):
          with open(spec_path) as f:
              spec = yaml.safe_load(f)

          parsed = parse_spec(spec)
          if not parsed.get("valid"):
              raise ValueError(f"Invalid spec: {parsed.get('errors')}")

          return load_flow_from_spec(spec)

5. **Error Handling**: Configure error handlers in DSL

   .. code-block:: yaml

      routines:
        critical_task:
          error_handler:
            strategy: "retry"
            max_retries: 5
            is_critical: true

        optional_task:
          error_handler:
            strategy: "continue"

See Also
--------

* :doc:`flows` - Flow class documentation
* :doc:`serialization` - Serialization and persistence
* :doc:`../api_reference/index` - Complete API reference
