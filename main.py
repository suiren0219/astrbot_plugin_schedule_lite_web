"""课表 Lite 网页伴侣（astrbot_plugin_schedule_lite_web）。

把课表 Lite 的使用手册上线成一个独立的只读网页，部署在 AstrBot 所在服务器上；
群里发链接而不是图片，省流量也不刷屏。

⚠️ 端口提醒：插件会在 web_port（默认 8766）监听 HTTP。云服务器必须在
安全组 / 防火墙放行该端口（TCP 入方向），否则外部访问不了。
"""

from __future__ import annotations

import asyncio
import re
import json
import socket
import time
from html import escape
from pathlib import Path

from aiohttp import web

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter as filter
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_schedule_lite_web"
MAIN_PLUGIN_REPO = "https://github.com/suiren0219/astrbot_plugin_schedule_lite"
PLUGIN_DIR = Path(__file__).resolve().parent

PAGE_CSS = """
:root{
  --bg:#f5f7fb; --card:#ffffff; --line:#e2e8f0; --text:#0f172a; --muted:#64748b;
  --accent:#2563eb; --accent-soft:#dbeafe; --soft:#f8fafc;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0b1220; --card:#111a2c; --line:#26314a; --text:#f8fafc; --muted:#94a3b8;
        --accent:#60a5fa; --accent-soft:#1e3a5f; --soft:#17233a; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  line-height:1.7}
.wrap{max-width:860px;margin:0 auto;padding:20px 16px 48px}
header.site{padding:26px 4px 14px}
header.site .brand{font-size:13px;letter-spacing:.12em;color:var(--accent);font-weight:700}
header.site h1{margin:6px 0 4px;font-size:26px}
header.site p{margin:0;color:var(--muted);font-size:14px}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 22px}
nav.toc a{padding:6px 12px;border-radius:999px;background:var(--card);border:1px solid var(--line);
  color:var(--text);text-decoration:none;font-size:13px}
nav.toc a:hover{border-color:var(--accent);color:var(--accent)}
article.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin:0 0 16px}
article.card h1{font-size:22px;margin:4px 0 14px}
article.card h2{font-size:19px;margin:22px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
article.card h2:first-of-type{border-top:none;padding-top:0}
article.card h3{font-size:16px;margin:16px 0 8px}
article.card p{margin:8px 0}
article.card ul,article.card ol{margin:8px 0;padding-left:22px}
article.card li{margin:4px 0}
article.card blockquote{margin:10px 0;padding:10px 14px;border-left:3px solid var(--accent);
  background:var(--accent-soft);border-radius:0 12px 12px 0;color:var(--text)}
article.card code{background:var(--soft);border:1px solid var(--line);border-radius:6px;
  padding:1px 6px;font-size:13px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
article.card hr{border:none;border-top:1px solid var(--line);margin:18px 0}
article.card a{color:var(--accent);text-decoration:none}
article.card a:hover{text-decoration:underline}
section.anchor{scroll-margin-top:16px}
footer.site{color:var(--muted);font-size:13px;text-align:center;padding:18px 0 0}
footer.site a{color:var(--accent);text-decoration:none}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:18px}
a.cardlink{display:block;background:var(--card);border:1px solid var(--line);border-radius:18px;
  padding:18px 20px;color:var(--text);text-decoration:none;transition:border-color .15s}
a.cardlink:hover{border-color:var(--accent)}
a.cardlink b{font-size:16px}
a.cardlink small{display:block;color:var(--muted);margin-top:6px;line-height:1.6}
.warn{background:var(--accent-soft);border:1px solid var(--accent);border-radius:14px;
  padding:10px 14px;font-size:14px;margin:14px 0}
"""

PAGE_TMPL = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 课表 Lite</title>
<style>{css}</style>
</head><body>
<div class="wrap">
<header class="site">
  <div class="brand">SCHEDULE LITE</div>
  <h1>{title}</h1>
  <p>{subtitle}</p>
</header>
{body}
<footer class="site">
  课表 Lite 网页伴侣 · 数据只保存在机器人本地 ·
  <a href="{repo}" target="_blank" rel="noopener">GitHub 仓库</a>
</footer>
</div>
</body></html>"""


def _inline(text: str) -> str:
    """行内语法：**粗体**、`代码`、[链接](url)。先整体 escape 再插标记。"""
    text = escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _slug(text: str, index: int) -> str:
    head = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip()).strip("-")
    return f"{index}-{head[:24]}" if head else f"section-{index}"


def markdown_to_html(md: str) -> str:
    """够用的 Markdown 子集：标题 / 列表 / 引用 / 分隔线 / 段落 + 行内标记。

    连续的普通行与连续的引用行会合并成同一个段落 / 引用块（Markdown 软换行），
    避免一句话被硬拆成两个 <p>。
    """
    out: list[str] = []
    h2 = 0
    list_open = ""
    para: list[str] = []
    quote: list[str] = []

    def flush() -> None:
        if para:
            out.append(f"<p>{_inline(''.join(para))}</p>")
            para.clear()
        if quote:
            out.append(f"<blockquote>{_inline(''.join(quote))}</blockquote>")
            quote.clear()

    for raw in md.splitlines():
        stripped = raw.strip()
        if not stripped:
            if list_open:
                out.append(f"</{list_open}>")
                list_open = ""
            flush()
            continue
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            if list_open:
                out.append(f"</{list_open}>")
                list_open = ""
            flush()
            out.append("<hr>")
            continue
        match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if match:
            if list_open:
                out.append(f"</{list_open}>")
                list_open = ""
            flush()
            level = len(match.group(1))
            text = _inline(match.group(2))
            if level == 2:
                h2 += 1
                slug = _slug(re.sub(r"<[^>]+>", "", text), h2)
                out.append(
                    f'<h2 id="sec-{slug}" class="anchor">{text}'
                    f' <a href="#sec-{slug}" style="font-size:12px;opacity:.5">#</a></h2>'
                )
            else:
                out.append(f"<h{level}>{text}</h{level}>")
            continue
        if stripped.startswith(">"):
            if list_open:
                out.append(f"</{list_open}>")
                list_open = ""
            flush_para_only = bool(para)
            if flush_para_only:
                flush()
            quote.append(stripped.lstrip("> "))
            continue
        match = re.match(r"^[-*]\s+(.*)$", stripped)
        if match:
            if list_open != "ul":
                flush()
                if list_open:
                    out.append(f"</{list_open}>")
                out.append("<ul>")
                list_open = "ul"
            out.append(f"<li>{_inline(match.group(1))}</li>")
            continue
        match = re.match(r"^\d+[.、]\s+(.*)$", stripped)
        if match:
            if list_open != "ol":
                flush()
                if list_open:
                    out.append(f"</{list_open}>")
                out.append("<ol>")
                list_open = "ol"
            out.append(f"<li>{_inline(match.group(1))}</li>")
            continue
        if list_open:
            out.append(f"</{list_open}>")
            list_open = ""
        if quote:
            flush()
        para.append(stripped)
    if list_open:
        out.append(f"</{list_open}>")
    flush()
    return "\n".join(out)


def _plain_preview(md: str, limit: int = 46) -> str:
    """章节卡片的一句预览：取第一段普通文字。"""
    for raw in md.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        text = re.sub(r"\*\*|`|\[([^\]]+)\]\([^)]*\)", r"\1", line)
        return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def split_sections(md: str) -> list[tuple[str, str]]:
    """按 `## 标题` 切分章节；h1 与引言并入第一节。返回 [(标题, markdown)]。"""
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current: list[str] = []
    for raw in md.splitlines():
        match = re.match(r"^##\s+(.+)$", raw.strip())
        if match:
            if current_title or current:
                sections.append((current_title, current))
            current_title = match.group(1).strip()
            current = [f"## {current_title}"]
        else:
            current.append(raw)
    if current_title or current:
        sections.append((current_title, current))
    # 首节去掉 h1 大标题（页头已经显示了），避免重复
    if sections:
        title, lines = sections[0]
        lines = [line for line in lines if not line.startswith("# ")]
        sections[0] = (title or "简介", lines)
    return [(title or "简介", "\n".join(lines).strip()) for title, lines in sections]


@register(
    "schedule_lite_web",
    "suiren0219",
    "课表 Lite 网页伴侣：把使用手册上线为只读网页，群里发链接不发图",
    "v0.1.0",
)
class ScheduleLiteWebPlugin(Star):
    """独立 HTTP 服务 + /课表网页 指令；不提供任何课表数据端点。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._server_task: asyncio.Task | None = None
        self._help_cache: tuple[float, str] = (0.0, "")
        self._server_task = asyncio.create_task(self._start_server())

    # ------------------------------------------------------------- 配置

    def _cfg(self, key: str, default):
        try:
            return self.config.get(key, default)
        except Exception:  # noqa: BLE001
            return getattr(self.config, key, default)

    def _external_base(self) -> str:
        """发到群里的地址：优先自定义域名（支持反代），否则本机 IP:端口。"""
        raw = str(self._cfg("external_base_url", "") or "").strip().rstrip("/")
        if raw:
            return raw
        return f"http://{self._lan_ip()}:{self._port()}"

    @staticmethod
    def _lan_ip() -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(("223.5.5.5", 80))
                return sock.getsockname()[0]
            finally:
                sock.close()
        except Exception:  # noqa: BLE001
            return "127.0.0.1"

    def _host(self) -> str:
        return str(self._cfg("web_host", "0.0.0.0") or "0.0.0.0")

    def _port(self) -> int:
        try:
            return max(1, min(int(self._cfg("web_port", 8766)), 65535))
        except (TypeError, ValueError):
            return 8766

    # ------------------------------------------------------------- 文档

    def _help_md_path(self) -> Path:
        """优先主插件目录的帮助文档，保证和主插件版本一致；找不到用自带副本。"""
        custom = str(self._cfg("main_plugin_dir", "") or "").strip()
        candidates: list[Path] = []
        if custom:
            candidates.append(Path(custom) / "docs" / "help.md")
        # 默认与附属插件同目录（都在 data/plugins/ 下）
        candidates.append(
            PLUGIN_DIR.parent / "astrbot_plugin_schedule_lite" / "docs" / "help.md"
        )
        candidates.append(PLUGIN_DIR / "docs" / "help.md")
        for path in candidates:
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
        return PLUGIN_DIR / "docs" / "help.md"

    def _help_markdown(self) -> str:
        path = self._help_md_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        cached_mtime, cached_md = self._help_cache
        if cached_md and mtime == cached_mtime:
            return cached_md
        try:
            md = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] 读取帮助文档失败: {exc}")
            md = "# 课表 Lite\n\n帮助文档暂时读取失败，请稍后刷新。"
        self._help_cache = (mtime, md)
        return md

    def _sections(self) -> list[tuple[str, str]]:
        return split_sections(self._help_markdown())

    def _help_html(self) -> str:
        return markdown_to_html(self._help_markdown())

    # ------------------------------------------------------------- 页面

    def _render(self, title: str, subtitle: str, body: str) -> str:
        return PAGE_TMPL.format(
            title=escape(title), subtitle=escape(subtitle), body=body,
            css=PAGE_CSS, repo=MAIN_PLUGIN_REPO,
        )

    async def _h_index(self, request: web.Request) -> web.Response:
        body = """
<article class="card">
  <h1>网页版帮助，群里不发图</h1>
  <p>课表 Lite 的完整使用手册放在这里，群里直接发链接即可，省下图片流量。
  课表数据始终只保存在机器人本地，本站只展示帮助内容。</p>
  <div class="warn">⚠️ 部署提醒：请在云服务器的安全组 / 防火墙放行本服务端口
  （TCP 入方向），否则外部无法访问。用裸 IP 链接会把服务器 IP 暴露给群里所有人，
  建议反代到个人域名（见插件 README 的安全提醒）。</div>
  <div class="cards">
    <a class="cardlink" href="/help"><b>📖 使用手册</b>
      <small>按章节浏览：导入、查询、请假调课、状态排行、提醒与面板</small></a>
    <a class="cardlink" href="/help/all"><b>📚 完整手册</b>
      <small>全部章节放在一页，适合 Ctrl+F 搜索</small></a>
    <a class="cardlink" href="{repo}" target="_blank" rel="noopener"><b>🧩 主插件仓库</b>
      <small>astrbot_plugin_schedule_lite · 版本与更新日志</small></a>
  </div>
</article>"""
        return web.Response(
            text=self._render("课表 Lite", "帮助手册 · 网页版", body),
            content_type="text/html", charset="utf-8",
        )

    async def _h_help(self, request: web.Request) -> web.Response:
        """目录页：每个章节一张二级入口卡片。"""
        sections = self._sections()
        cards = "".join(
            f'<a class="cardlink" href="/help/{index}"><b>{index}. {escape(title)}</b>'
            f"<small>{escape(_plain_preview(md))}</small></a>"
            for index, (title, md) in enumerate(sections, start=1)
        )
        body = f"""
<article class="card">
  <h1>使用手册</h1>
  <p>点开单个章节查看，或看<a href="/help/all">完整手册</a>。</p>
  <div class="cards">{cards}</div>
</article>"""
        return web.Response(
            text=self._render("使用手册", "选择一个章节", body),
            content_type="text/html", charset="utf-8",
        )

    async def _h_section(self, request: web.Request) -> web.Response:
        sections = self._sections()
        try:
            index = int(request.match_info["sid"])
        except (KeyError, ValueError):
            raise web.HTTPNotFound(text="章节不存在") from None
        if not 1 <= index <= len(sections):
            raise web.HTTPNotFound(text="章节不存在")
        title, md = sections[index - 1]
        nav = []
        if index > 1:
            nav.append(f'<a href="/help/{index - 1}">← {escape(sections[index - 2][0])}</a>')
        nav.append('<a href="/help">目录</a>')
        if index < len(sections):
            nav.append(f'<a href="/help/{index + 1}">{escape(sections[index][0])} →</a>')
        body = (
            '<article class="card">'
            f'<nav class="toc">{"".join(nav)}</nav>'
            f"{markdown_to_html(md)}"
            f'<nav class="toc">{"".join(nav)}</nav>'
            "</article>"
        )
        return web.Response(
            text=self._render(f"{index}. {title}", "使用手册 · 网页版", body),
            content_type="text/html", charset="utf-8",
        )

    async def _h_all(self, request: web.Request) -> web.Response:
        html = self._help_html()
        links = re.findall(r'<h2 id="(sec-[^"]+)"[^>]*>([^<#]+)', html)
        toc = ""
        if links:
            items = "".join(
                f'<a href="#{sid}">{escape(name.strip())}</a>' for sid, name in links
            )
            toc = f'<nav class="toc">{items}</nav>'
        body = f'<article class="card">{toc}\n{html}</article>'
        return web.Response(
            text=self._render("完整手册", "全部章节 · 网页版", body),
            content_type="text/html", charset="utf-8",
        )

    # ------------------------------------------------------------- 主插件联动

    def _companion_path(self) -> Path | None:
        """联动标记：写进主插件的数据目录，主插件读到后会在 /课表 帮助 附上网页链接。"""
        try:
            from astrbot.api.star import StarTools

            data_dir = Path(StarTools.get_data_dir())
        except Exception:  # noqa: BLE001
            return None
        # data/plugin_data/<本插件>/ → data/plugin_data/astrbot_plugin_schedule_lite/
        return data_dir.parent / "astrbot_plugin_schedule_lite" / "web_companion.json"

    def _publish_companion(self) -> None:
        path = self._companion_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "base_url": self._external_base(),
                        "port": self._port(),
                        "updated_at": time.time(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logger.info(f"[{PLUGIN_NAME}] 已向主插件发布网页地址: {self._external_base()}")
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] 联动标记写入失败（主插件不会显示网页链接）: {exc}")

    def _revoke_companion(self) -> None:
        path = self._companion_path()
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------- 服务

    async def _start_server(self) -> None:
        if not bool(self._cfg("web_enabled", True)):
            logger.info(f"[{PLUGIN_NAME}] web_enabled=false，网页服务未启动")
            return
        app = web.Application()
        app.router.add_get("/", self._h_index)
        app.router.add_get("/help", self._h_help)
        app.router.add_get("/help/all", self._h_all)
        app.router.add_get("/help/{sid}", self._h_section)
        self._runner = web.AppRunner(app, access_log=None)
        try:
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host(), self._port())
            await self._site.start()
            self._publish_companion()
            logger.info(
                f"[{PLUGIN_NAME}] 网页服务已启动 http://{self._lan_ip()}:{self._port()}"
                "（记得在安全组/防火墙放行该端口）"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[{PLUGIN_NAME}] 网页服务启动失败（端口被占用？）: {exc}")
            await self._stop_server()

    async def _stop_server(self) -> None:
        if self._site is not None:
            try:
                await self._site.stop()
            except Exception:  # noqa: BLE001
                pass
            self._site = None
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception:  # noqa: BLE001
                pass
            self._runner = None

    async def terminate(self) -> None:
        if self._server_task is not None:
            self._server_task.cancel()
            self._server_task = None
        await self._stop_server()
        self._revoke_companion()

    # ------------------------------------------------------------- 指令

    def _origin_hint(self) -> str:
        base = self._external_base()
        return f"{base}/help"

    def _link_reply(self) -> str:
        base = self._external_base()
        text = (
            "📖 课表 Lite 使用手册（网页版，不刷屏）\n"
            f"{base}/help\n"
            "手机浏览器打开即可；导入、查询、请假调课、状态排行都在里面。"
        )
        # 裸 IP 链接发到群里 = 公开服务器 IP，可被扫描；务必提醒
        if re.match(r"^http://\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?/", base + "/"):
            text += (
                "\n⚠️ 当前链接直接暴露服务器 IP，可能被扫描攻击；"
                "建议反代到个人域名并把 external_base_url 设为域名地址。"
            )
        return text

    @filter.command("课表网页")
    async def cmd_web_link(self, event):
        """发网页版帮助链接，不发图。"""
        yield event.plain_result(self._link_reply())
        event.stop_event()

    @filter.command("课表帮助网页")
    async def cmd_web_link_alt1(self, event):
        yield event.plain_result(self._link_reply())
        event.stop_event()

    @filter.command("课表链接")
    async def cmd_web_link_alt2(self, event):
        yield event.plain_result(self._link_reply())
        event.stop_event()
