# astrbot_plugin_token_display

在 AstrBot 每条 LLM 回复末尾展示 Token 消耗统计，支持模块拆分、缓存输入、消息分段和计费模式。

## 功能

- 在 LLM 回复末尾自动追加 Token 消耗（prompt / completion / total）
- 支持 `/tkn on` / `/tkn off` 指令按群或私聊开关
- 白名单机制：群聊和私聊均生效，按 QQ 号或群号配置
- 输入/输出/总量模块可独立开关
- 输入 token 支持三种显示模式：总输入、缓存拆分、完整明细
- 可选消息分段：token 信息与原回复分离为独立消息
- 计费模式：按 API 定价自动计算费用

## 指令

- `/tkn on`：开启当前群/私聊的 token 显示
- `/tkn off`：关闭当前群/私聊的 token 显示

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `whitelist` | list | `[]` | 白名单（QQ号或群号），群聊+私聊均生效，空则全部可用 |
| `show_input_tokens` | bool | true | 是否显示输入 token 块 |
| `show_output_tokens` | bool | true | 是否显示输出 token 块 |
| `show_total_tokens` | bool | true | 是否显示总量 token 块 |
| `input_token_display_mode` | string | total_only | 输入显示模式：total_only / cached_split / full_detail |
| `split_token_message` | bool | false | 是否将 token 信息与原回复分段为独立消息 |
| `enable_billing` | bool | false | 是否启用计费显示 |
| `input_price_per_1m_tokens` | float | 0.0 | 每百万输入 token 价格（美元） |
| `output_price_per_1m_tokens` | float | 0.0 | 每百万输出 token 价格（美元） |
| `cached_input_price_per_1m_tokens` | float | 0.0 | 每百万缓存输入 token 价格（美元） |
| `billing_display_mode` | string | append | 计费显示模式：append（追加）/ replace（替换） |

## 效果示例

```
📊 Token: ↑1234 ↓567 = 1801
```

缓存拆分模式：
```
📊 Token: ↑cached:800 other:434 ↓567 = 1801
```

计费模式（append）：
```
📊 Token: ↑1234 ↓567 = 1801 💰 $0.0423
```

计费模式（replace）：
```
💰 $0.0423
```

## 安装

将本插件文件夹放入 AstrBot 的 `data/plugins/` 目录，在 WebUI 插件管理页面加载后重启即可。

## 许可

MIT License
