Analysis and Visualization
==========================

Routilux provides powerful analysis and visualization tools for understanding your workflows and routines. These tools use AST (Abstract Syntax Tree) analysis to extract information from code and generate visual diagrams.

When to Use Analysis Tools
---------------------------

Use analysis tools when:

* You need to document workflow structure automatically
* You want to visualize routine dependencies
* You need to generate documentation from code
* You want to understand how routines are connected
* You need to audit workflow structure

Routine Analysis
----------------

Analyze individual routine files using AST:

.. code-block:: python

   from routilux import analyze_routine_file

   # Analyze a routine file
   analysis = analyze_routine_file("myapp/routines/data_processor.py")

   # Print analysis
   print(analysis.to_json(indent=2))

Output includes:

* **Routine name**: Class name and module
* **Slots**: Input slots with parameters
* **Events**: Output events with parameters
* **Methods**: All methods in the routine
* **Configuration**: Set configuration values
* **Docstrings**: Extracted documentation

Example output:

.. code-block:: json

   {
     "file_path": "myapp/routines/data_processor.py",
     "module_name": "myapp.routines.data_processor",
     "class_name": "DataProcessor",
     "docstring": "Processes data from database.",
     "slots": [
       {
         "name": "input",
         "handler": "process",
         "max_queue_length": 1000,
         "watermark": 0.8
       }
     ],
     "events": [
       {
         "name": "output",
         "output_params": ["result", "status"]
       }
     ],
     "methods": [
       {
         "name": "process",
         "parameters": ["data", "kwargs"],
         "docstring": "Process input data."
       }
     ],
     "config": {
       "timeout": 30,
       "batch_size": 100
     }
   }

Workflow Analysis
----------------

Analyze entire workflow structure:

.. code-block:: python

   from routilux import analyze_workflow

   # Create flow
   flow = Flow(flow_id="my_workflow")
   # ... add routines and connections ...

   # Analyze workflow
   analysis = analyze_workflow(flow)

   # Print as JSON
   print(analysis.to_json(indent=2))

Output includes:

* **Flow information**: ID, execution strategy, timeout
* **Routines**: List of routines with their details
* **Connections**: List of connections with routing information
* **Dependencies**: Dependency graph between routines

D2 Diagram Export
-------------------

Export workflows as D2 diagrams for visualization:

.. code-block:: python

   from routilux import analyze_workflow

   # Analyze workflow
   analysis = analyze_workflow(flow)

   # Export to D2 (standard mode)
   analysis.to_d2_format("workflow.d2", mode="standard")

   # Export to D2 (ultimate mode - enhanced)
   analysis.to_d2_format("workflow_ultimate.d2", mode="ultimate")

Rendering D2 Diagrams:

You can render D2 diagrams using the D2 tool:

.. code-block:: bash

   # Install D2
   brew install d2  # macOS
   # or visit https://d2lang.com/tour/install

   # Render to PNG
   d2 workflow.d2 -o workflow.png

   # Render to SVG
   d2 workflow.d2 -o workflow.svg

   # Render with layout engine
   d2 workflow.d2 -o workflow.png --layout=elk

Example D2 output (standard mode):

.. code-block:: d2

   direction: right

   extractor: DataExtractor {shape: database}
   validator: DataValidator {shape: process}
   transformer: DataTransformer {shape: process}
   exporter: DataExporter {shape: database}

   extractor.output -> validator.input
   validator.valid -> transformer.input
   transformer.output -> exporter.input

Example D2 output (ultimate mode):

.. code-block:: d2

   direction: right

   # Define styles
   style.fill #e0f2fe lightblue
   style.stroke #0288d1 blue

   # Nodes
   extractor: DataExtractor 🗄️ {
       style: fill
       slots: [input]
       events: [output]
       config: {source: database}
   }

   validator: DataValidator ✅ {
       style: fill
       slots: [input]
       events: [valid, invalid]
       config: {rules: 2}
   }

   transformer: DataTransformer ⚡ {
       style: fill
       slots: [input]
       events: [output]
       config: {batch_size: 100}
   }

   exporter: DataExporter 📤 {
       style: fill
       slots: [input]
       events: [output]
       config: {dest: s3://bucket}
   }

   # Edges with labels
   extractor.output -> validator.input: "raw data"
   validator.valid -> transformer.input: "validated"
   validator.invalid -> error_handler.input: "error": style.stroke-dash red
   transformer.output -> exporter.input: "transformed"

Markdown Documentation Generation
--------------------------------

Generate documentation from routines:

.. code-block:: python

   from routilux.analysis import RoutineAnalyzer, RoutineMarkdownFormatter

   # Analyze routine file
   analyzer = RoutineAnalyzer()
   routine_data = analyzer.analyze_file("myapp/routines/data_processor.py")

   # Generate markdown
   formatter = RoutineMarkdownFormatter()
   markdown = formatter.format(routine_data)

   # Save to file
   with open("data_processor.md", "w") as f:
       f.write(markdown)

Example markdown output:

.. code-block:: markdown

   # DataProcessor

   Processes data from database.

   ## Configuration

   * **timeout**: 30 seconds
   * **batch_size**: 100 items

   ## Input Slots

   ### `input`

   * Handler: `process`
   * Max queue length: 1000
   * Watermark: 0.8

   ## Output Events

   ### `output`

   Parameters:

   * **result**: Processed data
   * **status**: Processing status

   ## Methods

   ### `process(data, **kwargs)`

   Process input data.

   **Parameters**:

   * `data`: Input data to process
   * `**kwargs`: Additional keyword arguments

Advanced Usage
-------------

Batch Analysis:

.. code-block:: python

   import os
   from routilux import analyze_routine_file

   # Analyze all routines in directory
   routines_dir = "myapp/routines"
   all_analyses = []

   for filename in os.listdir(routines_dir):
       if filename.endswith(".py"):
           filepath = os.path.join(routines_dir, filename)
           analysis = analyze_routine_file(filepath)
           all_analyses.append(analysis)

   # Generate combined documentation
   for analysis in all_analyses:
       print(f"# {analysis.class_name}")
       print(f"**File:** {analysis.file_path}")
       print(f"**Slots:** {len(analysis.slots)}")
       print(f"**Events:** {len(analysis.events)}")
       print()

Workflow Comparison:

.. code-block:: python

   from routilux import analyze_workflow

   # Compare two workflows
   flow1 = Flow(flow_id="workflow_v1")
   # ... build flow1 ...

   flow2 = Flow(flow_id="workflow_v2")
   # ... build flow2 ...

   analysis1 = analyze_workflow(flow1)
   analysis2 = analyze_workflow(flow2)

   # Compare routines
   routines1 = {r.id for r in analysis1.routines}
   routines2 = {r.id for r in analysis2.routines}

   added = routines2 - routines1
   removed = routines1 - routines2

   print(f"Added routines: {added}")
   print(f"Removed routines: {removed}")

Dependency Analysis:

.. code-block:: python

   from routilux import analyze_workflow

   # Analyze workflow
   analysis = analyze_workflow(flow)

   # Build dependency graph
   dependencies = {}
   for conn in analysis.connections:
       source = conn.source_routine.id
       target = conn.target_routine.id
       dependencies.setdefault(source, []).append(target)

   # Find roots (routines with no incoming connections)
   all_routines = set(analysis.routine_ids)
   all_targets = set(target for targets in dependencies.values() for target in targets)
   roots = all_routines - all_targets

   print(f"Entry points (roots): {roots}")

   # Topological sort
   def topological_sort(graph):
       visited = set()
       order = []

       def visit(node):
           if node in visited:
               return
           visited.add(node)
           for neighbor in graph.get(node, []):
               visit(neighbor)
           order.append(node)

       for node in graph:
           visit(node)

       return order[::-1]

   execution_order = topological_sort(dependencies)
   print(f"Execution order: {execution_order}")

Automated Documentation:

.. code-block:: python

   import os
   from routilux.analysis import RoutineAnalyzer, RoutineMarkdownFormatter

   def generate_docs(routines_dir, output_dir):
       """Generate documentation for all routines."""

       os.makedirs(output_dir, exist_ok=True)
       index = []

       for filename in os.listdir(routines_dir):
           if not filename.endswith(".py"):
               continue

           filepath = os.path.join(routines_dir, filename)
           analyzer = RoutineAnalyzer()
           data = analyzer.analyze_file(filepath)

           # Generate markdown
           formatter = RoutineMarkdownFormatter()
           markdown = formatter.format(data)

           # Save
           output_path = os.path.join(output_dir, f"{data.class_name}.md")
           with open(output_path, "w") as f:
               f.write(markdown)

           index.append({
               "class": data.class_name,
               "file": filename,
               "doc": f"{data.class_name}.md"
           })

       # Generate index
       index_md = "# Routines\n\n"
       for item in index:
           index_md += f"## [{item['class']}]({item['doc']})\n\n"
           if item.get("docstring"):
               index_md += f"{item['docstring']}\n\n"

       with open(os.path.join(output_dir, "README.md"), "w") as f:
           f.write(index_md)

   # Generate docs
   generate_docs("myapp/routines", "docs/routines")

Integration with CI/CD
------------------------

Add analysis to CI/CD pipeline:

.. code-block:: yaml

   # .github/workflows/analyze.yml
   name: Analyze Workflows

   on: [push]

   jobs:
     analyze:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v2

         - name: Set up Python
           uses: actions/setup-python@v2
           with:
             python-version: '3.11'

         - name: Install dependencies
           run: |
             pip install -e .
             pip install d2

         - name: Analyze workflows
           run: |
             python -c "
             from routilux import analyze_workflow
             from myapp import my_flow

             analysis = analyze_workflow(my_flow)
             analysis.to_d2_format('workflow.d2', mode='ultimate')
             "

         - name: Generate diagram
           run: d2 workflow.d2 -o workflow.png

         - name: Upload diagrams
           uses: actions/upload-artifact@v2
           with:
             name: workflow-diagrams
             path: workflow.png

Best Practices
--------------

1. **Document Public APIs**: Use docstrings for all public methods

   .. code-block:: python

      class MyRoutine(Routine):
          """My routine for processing data."""

          def process(self, data):
              """Process the input data.

              Args:
                  data: The input data to process

              Returns:
                  Processed result
              """
              ...

2. **Use Configuration**: Document configuration in set_config()

   .. code-block:: python

      def __init__(self):
          super().__init__()
          # Document configuration
          self.set_config(
              timeout=30,  # Timeout in seconds
              batch_size=100,  # Batch size for processing
              retries=3  # Number of retries on failure
          )

3. **Version Control Diagrams**: Commit generated diagrams to track changes

4. **Automate Documentation**: Run analysis as part of CI/CD

5. **Review Dependencies**: Use analysis to identify circular dependencies or missing connections

See Also
--------

* :doc:`routines` - Routine class documentation
* :doc:`flows` - Flow class documentation
* :doc:`../api_reference/index` - Complete API reference
* `D2 Documentation <https://d2lang.com>`_ - D2 diagramming language
