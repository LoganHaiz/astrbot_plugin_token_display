import json
from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.star_tools import StarTools


class TokenDisplayPlugin(Star):
    """在 LLM 回复末尾自动显示 Token 消耗统计。

    指令：
      /tkn on  — 开启 token 显示
      /tkn off — 关闭 token 显示
      /tkn     — 查看当前状态
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # ---- 白名单（群号或QQ号，空列表 = 全部可用） ----
        self.whitelist: list[str] = config.get("whitelist", [])

        # ---- Token 显示模块开关 ----
        self.show_input_tokens: bool = config.get("show_input_tokens", True)
        self.show_output_tokens: bool = config.get("show_output_tokens", True)
        self.show_total_tokens: bool = config.get("show_total_tokens", True)

        # ---- 输入 token 缓存显示模式 ----
        self.input_token_display_mode: str = config.get(
            "input_token_display_mode", "total_only"
        )

        # ---- 消息分段适配 ----
        self.split_token_message: bool = config.get("split_token_message", False)

        # ---- 计费模式 ----
        self.enable_billing: bool = config.get("enable_billing", False)
        self.input_price_per_1m: float = config.get(
            "input_price_per_1m_tokens", 0.0
        )
        self.output_price_per_1m: float = config.get(
            "output_price_per_1m_tokens", 0.0
        )
        self.cached_input_price_per_1m: float = config.get(
            "cached_input_price_per_1m_tokens", 0.0
        )
        self.billing_display_mode: str = config.get(
            "billing_display_mode", "append"
        )

        # ---- 持久化数据目录和文件 ----
        self.data_dir: Path = StarTools.get_data_dir()
        self.data_file: Path = self.data_dir / "data.json"

        # 加载开关状态: {"groups": {group_id: bool}, "privates": {user_id: bool}}
        self._state: dict[str, dict[str, bool]] = self._load_data()

    # ------------------------------------------------------------------
    # 数据持久化
    # ------------------------------------------------------------------
    def _load_data(self) -> dict:
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("groups", {})
                data.setdefault("privates", {})
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"[token_display] 读取 data.json 失败: {e}，使用默认状态"
                )
        return {"groups": {}, "privates": {}}

    def _save_data(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"[token_display] 保存 data.json 失败: {e}")

    # ------------------------------------------------------------------
    # 开关判断
    # ------------------------------------------------------------------
    def _get_group_id(self, event: AstrMessageEvent) -> str:
        return event.get_group_id() or ""

    def _get_sender_id(self, event: AstrMessageEvent) -> str:
        return event.get_sender_id() or ""

    def _is_group_chat(self, event: AstrMessageEvent) -> bool:
        return bool(self._get_group_id(event))

    def _is_whitelisted(self, event: AstrMessageEvent) -> bool:
        """检查当前会话是否在白名单中。空白名单 = 全部可用。"""
        if not self.whitelist:
            return True
        if self._is_group_chat(event):
            return self._get_group_id(event) in self.whitelist
        else:
            return self._get_sender_id(event) in self.whitelist

    def _is_enabled(self, event: AstrMessageEvent) -> bool:
        """判断当前会话是否开启了 token 显示。"""
        if not self._is_whitelisted(event):
            return False
        if self._is_group_chat(event):
            gid = self._get_group_id(event)
            return self._state.get("groups", {}).get(gid, False)
        else:
            uid = self._get_sender_id(event)
            return self._state.get("privates", {}).get(uid, False)

    def _set_enabled(self, event: AstrMessageEvent, enabled: bool) -> None:
        """设置当前会话的开关状态并持久化。"""
        if self._is_group_chat(event):
            gid = self._get_group_id(event)
            self._state.setdefault("groups", {})[gid] = enabled
        else:
            uid = self._get_sender_id(event)
            self._state.setdefault("privates", {})[uid] = enabled
        self._save_data()

    # ------------------------------------------------------------------
    # 指令: /tkn on|off
    # ------------------------------------------------------------------
    @filter.command("tkn")
    async def tkn_command(self, event: AstrMessageEvent, action: str = ""):
        """处理 /tkn on /tkn off /tkn 指令。"""
        action = action.strip().lower()

        if not self._is_whitelisted(event):
            yield event.plain_result(
                "⚠️ 你不在 Token 显示白名单中，无法使用此功能。"
            )
            return

        if action == "on":
            self._set_enabled(event, True)
            yield event.plain_result("✅ Token 显示已开启")
        elif action == "off":
            self._set_enabled(event, False)
            yield event.plain_result("❌ Token 显示已关闭")
        else:
            status = "开启 ✅" if self._is_enabled(event) else "关闭 ❌"
            yield event.plain_result(
                f"🔧 Token 显示当前状态：{status}\n"
                f"使用 /tkn on 或 /tkn off 切换"
            )

    # ------------------------------------------------------------------
    # Utility: 安全获取 usage 属性（兼容不同命名约定）
    # ------------------------------------------------------------------
    @staticmethod
    def _get_usage_attr(usage, names: list[str], default: int = 0) -> int:
        """按优先级尝试从 usage 对象获取属性值。"""
        for name in names:
            val = getattr(usage, name, None)
            if val is not None:
                return int(val)
        return default

    # ------------------------------------------------------------------
    # LLM 响应钩子: 累积 token 用量
    # ------------------------------------------------------------------
    @filter.on_llm_response()
    async def on_llm_response(
        self, event: AstrMessageEvent, response: LLMResponse
    ):
        """每次 LLM 调用返回后，累积 token 使用量到 event extras 中。"""
        if response.usage is None:
            return

        accumulated: dict | None = event.get_extra("_token_usage_accum")
        if accumulated is None:
            accumulated = {
                "input": 0,
                "output": 0,
                "total": 0,
                "cached_input": 0,
            }
            event.set_extra("_token_usage_accum", accumulated)

        usage = response.usage
        accumulated["input"] += self._get_usage_attr(
            usage, ["input_tokens", "input"]
        )
        accumulated["output"] += self._get_usage_attr(
            usage, ["output_tokens", "output"]
        )
        accumulated["total"] += self._get_usage_attr(
            usage, ["total_tokens", "total"]
        )
        accumulated["cached_input"] += self._get_usage_attr(
            usage, ["cached_input_tokens"]
        )

    # ------------------------------------------------------------------
    # 构建显示文本
    # ------------------------------------------------------------------
    def _format_input_tokens(self, inp: int, cached: int) -> str:
        """根据 input_token_display_mode 格式化输入 token 字符串。"""
        if self.input_token_display_mode == "cached_split":
            other = inp - cached
            return f"↑cached:{cached} other:{other}"
        elif self.input_token_display_mode == "full_detail":
            return f"↑{inp} (cached:{cached} other:{inp - cached})"
        else:  # total_only
            return f"↑{inp}"

    def _build_token_display(self, accumulated: dict) -> str | None:
        """根据配置构建 token 显示字符串。返回 None 表示不显示。"""
        inp = accumulated.get("input", 0)
        out = accumulated.get("output", 0)
        tot = accumulated.get("total", 0)
        cached = accumulated.get("cached_input", 0)

        si = self.show_input_tokens
        so = self.show_output_tokens
        st = self.show_total_tokens

        # 什么都没开
        if not si and not so and not st:
            return None

        # 三个全开 → 紧凑格式
        if si and so and st:
            input_part = self._format_input_tokens(inp, cached)
            return f"📊 Token: {input_part} ↓{out} = {tot}"

        # 只开总量
        if st and not si and not so:
            return f"📊 Token: {tot}"

        # 其他组合
        parts: list[str] = []
        if si:
            parts.append(self._format_input_tokens(inp, cached))
        if so:
            parts.append(f"↓{out}")
        if st:
            parts.append(f"= {tot}")

        if not parts:
            return None

        return f"📊 Token: {' '.join(parts)}"

    def _build_billing_display(self, accumulated: dict) -> str | None:
        """根据配置构建计费显示字符串。返回 None 表示不显示。"""
        if not self.enable_billing:
            return None

        inp = accumulated.get("input", 0)
        out = accumulated.get("output", 0)
        cached = accumulated.get("cached_input", 0)

        cost = (
            inp * self.input_price_per_1m
            + out * self.output_price_per_1m
            + cached * self.cached_input_price_per_1m
        ) / 1_000_000

        return f"💰 ${cost:.4f}"

    # ------------------------------------------------------------------
    # 消息装饰钩子: 追加 token / 计费显示
    # ------------------------------------------------------------------
    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """在消息发送前，如果开启了 token 显示，追加统计信息。"""
        if not self._is_enabled(event):
            return

        accumulated: dict | None = event.get_extra("_token_usage_accum")
        if not accumulated or accumulated.get("total", 0) <= 0:
            return

        result = event.get_result()
        if result is None or not result.chain:
            return

        # 仅对 LLM 结果追加
        if not result.is_llm_result():
            return

        # 构建显示文本
        token_text = self._build_token_display(accumulated)
        billing_text = self._build_billing_display(accumulated)

        if self.enable_billing and self.billing_display_mode == "replace":
            # replace 模式：只显示计费信息
            final_text = billing_text
        else:
            # append 模式：token + 计费（计费也可能为 None）
            parts = []
            if token_text:
                parts.append(token_text)
            if billing_text:
                parts.append(billing_text)
            final_text = " | ".join(parts) if parts else None

        if not final_text:
            return

        # 消息分段适配
        if self.split_token_message:
            final_text = "\n" + final_text

        result.chain.append(Plain(final_text))

        logger.debug(
            f"[token_display] 追加显示: {final_text!r}"
        )
