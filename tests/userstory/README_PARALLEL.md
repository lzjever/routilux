# 并行测试使用指南

## 快速开始

### 安装依赖
```bash
uv sync --group dev
```

### 运行并行测试
```bash
# 使用自动检测CPU核心数（推荐）
make test-userstory-fast

# 或手动指定worker数量
uv run pytest tests/userstory/ -n 4 -m userstory

# 或使用auto
uv run pytest tests/userstory/ -n auto -m userstory
```

## 性能对比

### 串行执行
```bash
make test-userstory
# 时间: ~10分钟 (600秒)
```

### 并行执行（4核CPU）
```bash
make test-userstory-fast
# 时间: ~2-3分钟 (120-180秒)
# 提升: 3-5倍
```

### 并行执行（8核CPU）
```bash
make test-userstory-fast
# 时间: ~1-2分钟 (60-120秒)
# 提升: 5-10倍
```

## 注意事项

### Fixture Scope
- `setup_demo_flows`: `module` scope（同一文件内共享）
- `client`: `function` scope（每个测试独立）
- `reset_state`: `function` scope（每个测试前清理）

### 并行测试限制
1. 测试之间不能共享可变状态
2. 每个worker有独立的进程空间
3. Fixture需要在每个worker中独立初始化

### 如果遇到问题
```bash
# 回退到串行执行
make test-userstory

# 或使用更少的workers
uv run pytest tests/userstory/ -n 2 -m userstory
```

## 优化建议

1. **开发时**: 使用并行测试快速反馈
2. **调试时**: 使用串行测试便于调试
3. **CI/CD**: 使用auto自动检测CPU核心数
