# Misconfiguration Demo

This demo demonstrates potential issues when users incorrectly configure routine connections in routilux.

## Issues Demonstrated

### 1. Circular Connections
- **Problem**: Routines connected in a loop (A -> B -> A)
- **Risk**: Infinite loops if termination condition is never met
- **Example**: Processor -> Validator -> Processor (loopback)
- **Mitigation**: Always set max_iterations or termination conditions

### 2. Unconnected Events
- **Problem**: Events are emitted but no slots are connected to receive them
- **Risk**: Potential memory leaks if framework doesn't handle this correctly
- **Example**: `Processor.unconnected_event` emits but nothing receives it
- **Expected Behavior**: Framework should NOT create tasks for unconnected events

### 3. Unconnected Slots
- **Problem**: Slots are defined but never connected to any events
- **Risk**: Unused functionality, not a critical issue
- **Example**: `Processor.unconnected_slot` is defined but never receives data
- **Impact**: Minimal, just unused code

### 4. Memory Leak Prevention
- **Concern**: Excessive event emissions without handlers could fill up queues
- **Monitoring**: This demo includes a MemoryMonitor to track queue size and active tasks
- **Protection**: Framework should limit queue size and provide timeout mechanisms

## Scenarios

### Scenario 1: Controlled Loop
- Tests a circular connection that stops after `max_iterations`
- Expected: Loop continues until max_iterations, then stops and sends to Finalizer
- Demonstrates: Proper termination condition handling

### Scenario 2: Potential Infinite Loop
- Tests a circular connection with high validation threshold
- Expected: Loop continues until max_iterations, then stops
- Warning: If max_iterations is too high, this could run for a long time
- Demonstrates: Need for timeout protection

### Scenario 3: Unconnected Events
- Tests if emitting to unconnected events causes memory leaks
- Expected: Events are emitted but no tasks are created (no slots connected)
- Demonstrates: Framework's handling of orphaned events

## Running the Demo

```bash
cd /home/percy/works/mygithub/routilux
conda activate mbos
python -m playground.misconfiguration_demo.misconfiguration_demo
```

## Key Findings

1. **Circular Connections**: Framework should handle controlled loops (with termination condition), but infinite loops can occur if termination condition is never met. Framework should provide timeout protection.

2. **Unconnected Events**: Events emitted to unconnected slots should NOT create tasks. This prevents memory leaks from orphaned events. Framework should handle this gracefully.

3. **Unconnected Slots**: Slots that are never connected simply don't receive data. This is not a problem, just unused functionality.

4. **Memory Leak Prevention**: Framework should limit queue size, provide timeout mechanisms, and detect/prevent infinite loops.

## Recommendations

1. Always set max_iterations or termination conditions for loops
2. Use timeouts when executing flows with potential loops
3. Monitor queue size and active tasks during execution
4. Remove or connect unused events/slots to avoid confusion
5. Use the MemoryMonitor class to track resource usage during development

