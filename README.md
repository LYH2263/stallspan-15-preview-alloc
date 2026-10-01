# StallSpan 市集摊档开间

沿街段一维 First-Fit 开间分配，挡柱不可被摊位跨越，输出分配图与放不下清单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4700 |
| API | http://localhost:9700 |
| API 文档 | http://localhost:9700/docs |
| Postgres | localhost:5448 |

健康检查：`GET http://localhost:9700/api/health`

## 使用说明

1. 在「集日」「街段」确认开市日与可用宽度。
2. 在「摊主」「挡柱」维护需求宽度与障碍位置（摊主宽度可就地编辑保存）。
3. 打开「分配图」：先点选一个柱间空档 →「试摆」只在该空档内按优先序从左填空，**不写入运行表**；侧栏查看放得下/放不下结论。
4. 确认结论无误后按侧栏内绿色「确认入库」，才按从左填空落库一行；主图、运行抽屉与「放不下」页对应该空档内同一份结果。
5. 未点选空档时试摆/确认都会提示「请先点选一个柱间空档」；「整段重排」仍对全段重新分配并入库。
6. 在「放不下」查看的永远只是**已入库运行**的拒绝清单，试摆结论不会出现在此页。

## 开发与测试

```bash
docker compose exec api pytest -q
```
