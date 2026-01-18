# Userstory Tests Performance Optimization Summary

## 已完成的优化

### 1. ✅ 添加并行测试支持
- **添加**: `pytest-xdist>=3.0.0` 到依赖
- **新增命令**: `make test-userstory-fast` (并行执行)
- **预期提升**: 3-8倍（取决于CPU核心数）

### 2. ✅ 减少Sleep时间
- `0.5s` → `0.1s` (5倍减少)
- `2s` → `0.5s` (4倍减少)  
- `3s` → `1s` (3倍减少)
- `1s` → `0.3s` (3倍减少)
- **预期提升**: 20-30%

### 3. ✅ 优化Flow创建
- 添加flow存在检查，跳过重复创建
- **预期提升**: 10-20%

## 使用方法

### 并行测试（推荐）
```bash
# 自动检测CPU核心数
make test-userstory-fast

# 或手动指定
uv run pytest tests/userstory/ -n 4 -m userstory
```

### 串行测试（调试时）
```bash
make test-userstory
```

## 性能对比

### 优化前
- **时间**: ~10分钟 (600秒)
- **方式**: 串行执行
- **平均**: ~4秒/测试

### 优化后（4核CPU，并行）
- **时间**: ~2-3分钟 (120-180秒)
- **方式**: 并行执行 + sleep优化
- **提升**: **3-5倍**

### 优化后（8核CPU，并行）
- **时间**: ~1-2分钟 (60-120秒)
- **方式**: 并行执行 + sleep优化
- **提升**: **5-10倍**

## 为什么不能使用Module Scope Fixture

### 问题
- 并行测试时，每个worker进程有独立的状态空间
- Module scope的fixture在一个worker中设置，其他worker看不到
- 会导致测试失败

### 解决方案
- 保持`function` scope，确保每个worker独立初始化
- 通过减少sleep和优化flow创建来提升性能
- 并行执行本身就能带来最大的性能提升

## 进一步优化建议

1. **使用pytest-benchmark**: 监控性能回归
2. **测试分组**: 将慢测试和快测试分开运行
3. **条件跳过**: 对于可选功能使用`pytest.skip()`
4. **Mock慢操作**: 对于测试逻辑而非性能的场景

## 监控性能

```bash
# 查看最慢的测试
uv run pytest tests/userstory/ --durations=10

# 并行执行并查看时间
make test-userstory-fast
```
