# Userstory Tests Performance Optimization Guide

## 问题分析

### 当前性能
- **测试数量**: 144个测试
- **执行时间**: ~10分钟 (600秒)
- **平均每个测试**: ~4秒

### 性能瓶颈

1. **串行执行**: 所有测试串行运行，无法利用多核CPU
2. **Fixture重复设置**: 每个测试都重新创建flows和routines
3. **过多的sleep**: 53个sleep调用，累计等待时间很长
4. **Fixture scope**: 所有fixture都是`function`级别，无法共享

## 优化方案

### 1. 并行测试 (pytest-xdist)

**已添加**: `pytest-xdist>=3.0.0` 到依赖

**使用方法**:
```bash
# 自动检测CPU核心数
make test-userstory-parallel

# 或手动指定worker数量
uv run pytest tests/userstory/ -n 4 -m userstory

# 或使用auto（推荐）
uv run pytest tests/userstory/ -n auto -m userstory
```

**预期提升**: 4-8倍速度提升（取决于CPU核心数）

### 2. Fixture Scope优化

**已优化**:
- `setup_demo_flows`: `function` → `module` (同一模块内共享flows)

**原理**: 
- `module` scope: 同一测试文件内的所有测试共享fixture
- 减少重复创建flows和routines的时间

**预期提升**: 30-50%速度提升

### 3. 减少Sleep时间

**已优化**:
- `0.5s` → `0.1s` (5倍减少)
- `2s` → `0.5s` (4倍减少)
- `3s` → `1s` (3倍减少)
- `1s` → `0.3s` (3倍减少)

**预期提升**: 20-30%速度提升

### 4. 进一步优化建议

#### A. 使用更高效的等待机制
```python
# 替换 sleep + 轮询
# 使用 wait endpoint
wait_response = client.post(
    f"/api/v1/jobs/{job_id}/wait",
    params={"timeout": 2.0},
)
```

#### B. Mock慢操作
对于测试逻辑而非性能的场景，可以mock `time.sleep()`:
```python
@patch('time.sleep')
def test_something(mock_sleep):
    # 测试逻辑
    pass
```

#### C. 使用pytest-asyncio
对于异步操作，使用`pytest-asyncio`可以更好地处理并发。

## 预期性能提升

### 优化前
- 串行执行: 600秒 (10分钟)
- 平均每个测试: 4秒

### 优化后（4核CPU）
- 并行执行 (4 workers): ~150秒 (2.5分钟)
- Fixture优化: ~100秒 (1.7分钟)
- Sleep优化: ~70秒 (1.2分钟)
- **总计提升**: **约8-10倍**

### 优化后（8核CPU）
- 并行执行 (8 workers): ~75秒 (1.25分钟)
- **总计提升**: **约8倍**

## 使用建议

### 开发时
```bash
# 快速反馈，使用并行测试
make test-userstory-parallel
```

### CI/CD
```bash
# 使用auto检测CPU核心数
pytest tests/userstory/ -n auto -m userstory
```

### 调试时
```bash
# 串行执行，便于调试
make test-userstory
```

## 注意事项

### 并行测试的限制

1. **状态隔离**: 确保测试之间没有共享状态
2. **Fixture清理**: `module` scope的fixture需要确保清理
3. **资源竞争**: 避免测试之间竞争同一资源

### 当前实现

- ✅ `setup_demo_flows` 使用 `module` scope
- ✅ `client` fixture 仍使用 `function` scope（确保隔离）
- ✅ `reset_state` fixture 确保每个测试前清理状态

## 监控性能

```bash
# 查看最慢的10个测试
uv run pytest tests/userstory/ --durations=10

# 查看每个测试的详细时间
uv run pytest tests/userstory/ --durations=0
```

## 进一步优化方向

1. **使用pytest-benchmark**: 监控性能回归
2. **测试分组**: 将慢测试和快测试分开
3. **条件跳过**: 对于可选功能，使用`pytest.skip()`
4. **缓存**: 对于不变的flows，使用session scope
