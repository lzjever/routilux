# Playground

This directory contains various demonstration systems showcasing routilux capabilities.

## Available Demos

### LLM Agent Cross-Host Interrupt and Recovery

**Location**: `llm_agent_cross_host/`

A complete demonstration of LLM agent workflow with cross-host interrupt and recovery capabilities.

**Features**:
- Active interruption from within routines
- State persistence to cloud storage
- Cross-host recovery and continuation
- Comprehensive logging system

**Documentation**: See `llm_agent_cross_host/README.md` for complete documentation.

**Run Demo**:
```bash
cd /home/developer/workspace/routilux
conda activate mbos
python -m playground.llm_agent_cross_host.cross_host_demo
```

## Structure

```
playground/
├── __init__.py                    # Package initialization
├── README.md                      # This file
└── llm_agent_cross_host/          # LLM Agent demo
    ├── __init__.py
    ├── README.md                  # Complete documentation
    ├── logger.py                  # Logging utility
    ├── mock_llm.py                # Mock LLM service
    ├── mock_storage.py            # Mock cloud storage
    ├── enhanced_routine.py        # Enhanced Routine base class
    ├── llm_agent_routine.py       # LLM Agent Routine
    └── cross_host_demo.py         # Complete demonstration
```

## Adding New Demos

When adding a new demo:

1. Create a new subdirectory under `playground/`
2. Add all demo files to the subdirectory
3. Create a `README.md` in the subdirectory with complete documentation
4. Update this `README.md` to include the new demo
5. Optionally add to Sphinx documentation in `docs/source/examples/`

## Documentation

Each demo should include:
- Feature overview
- Design patterns
- Code overview
- Usage examples
- Performance analysis (if applicable)
- Extension guide
