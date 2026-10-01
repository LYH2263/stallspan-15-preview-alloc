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
2. 在「摊主」「挡柱」维护需求宽度与障碍位置（分配图底部排队条也可直接改摊宽）。
3. 打开「分配图」，先**点选东街段上的一个柱间空档**（图上热区或侧栏编号）。
4. 点「试摆」：只在该空档内按优先序（优先级、再 id）从左填空；**试摆不落库**，开间运行表一行不增，放不下页只会标为「试摆结论 · 未入库」。
5. 点「确认落库」：与试摆同一个引擎函数，放置/拒绝集合必然一致，确认后才写入运行表一行；主图、「运行抽屉」、「放不下」三处都对应该运行。
6. 未选空档时试摆与确认都会以「未选空档」拒绝；非法空档编号报错且不影响已有运行。

主要接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/allocate/spans?segment_id=1` | 柱间空档清单（点选用） |
| POST | `/api/allocate/preview` | 试摆，body `{segment_id, span_index}`；纯计算不写库 |
| POST | `/api/allocate/confirm` | 确认落库；无需会话令牌；只写所选单空档 |
| GET | `/api/allocate/runs` / `/api/allocate/run/{id}` / `/api/allocate/latest` | 已入库运行（抽屉/主图/放不下） |
| PATCH | `/api/vendors/{id}` | 改摊宽 `{stall_width_m}`，下次试摆即时生效 |

## 开发与测试

```bash
docker compose exec api pytest -q
```
