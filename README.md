# 课表 Lite 网页伴侣（astrbot_plugin_schedule_lite_web）

[课表 Lite](https://github.com/suiren0219/astrbot_plugin_schedule_lite) 的附属插件：
把完整使用手册上线成一个只读网页，部署在你自己的服务器上。群里发 **链接** 而不是图片，
省流量也不刷屏；手机浏览器打开自动跟随系统深色模式。

```
群友：/课表网页
机器人：📖 课表 Lite 使用手册（网页版，不刷屏）
        https://kb.example.com/help
        手机浏览器打开即可；导入、查询、请假调课、状态排行都在里面。
```

## ⚠️ 部署前提：放行端口（重要）

插件会在 AstrBot 所在服务器上监听一个独立端口（默认 **8766**，TCP）。
**云服务器必须在安全组 / 防火墙里放行该端口（TCP 入方向），否则外部无法访问**：

- 阿里云 / 腾讯云 / 华为云：控制台 → 安全组 → 添加入方向规则，端口 `8766`，授权对象 `0.0.0.0/0`
- 服务器自带防火墙（firewalld / ufw / iptables）同样要放行
- 改了 `web_port` 配置后，记得同步放行新端口

不放行端口时，只有服务器本机能打开网页。

## 🔒 安全提醒：裸 IP 链接会暴露服务器（重要）

- 不配置 `external_base_url` 时，`/课表网页` 发出去的是 `http://服务器IP:端口` 这样的
  **裸 IP 链接**——群里每个人（以及任何截图转发者）都能看到你的服务器 IP，
  IP 一旦泄露就可能被端口扫描、爆破尝试等攻击
- **强烈建议**：用自己的域名 + Nginx/Caddy 反代（隐藏源站 IP），再把
  `external_base_url` 设成域名地址；有条件可以叠一层 CDN（如 Cloudflare 小云朵）
- 最稳妥的组合：`web_host` 改 `127.0.0.1`（不对公网开端口）+ 域名反代，
  安全组只放行 443，连 8766 都不用放行
- 本站只展示帮助文档，没有课表数据和任何写接口，但仍建议走 HTTPS

安装前请先读[部署安全指南](https://github.com/suiren0219/astrbot_plugin_schedule_lite/blob/main/docs/deploy-security.md)（端口放行 + IP 保护）。

## 安装

1. 把 `astrbot_plugin_schedule_lite_web` 目录放进 AstrBot 的 `data/plugins/`
2. 面板启用插件（需要先安装主插件课表 Lite）
3. 浏览器访问 `http://服务器IP:8766/` 确认能看到帮助首页

## 配置

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `web_enabled` | `true` | 关闭后网页服务不启动 |
| `web_host` | `0.0.0.0` | 监听地址；只在本机反代可改 `127.0.0.1` 更安全 |
| `web_port` | `8766` | 监听端口，**需放行** |
| `external_base_url` | 空 | 对外访问地址（个人域名），留空用 `http://本机IP:端口` |
| `main_plugin_dir` | 空 | 主插件目录；留空自动按同级目录查找 |

## 绑定个人域名（推荐）

帮助页是纯静态内容，用 Nginx / Caddy 反代到自己的域名即可：

```nginx
# Nginx 示例：https://kb.example.com/help → 本机 8766
server {
    listen 443 ssl;
    server_name kb.example.com;
    location /schedule/ {
        proxy_pass http://127.0.0.1:8766/;
        proxy_set_header Host $host;
    }
}
```

反代后把 `external_base_url` 设成 `https://kb.example.com/schedule`，
群里发出去的链接就会自动带上你的域名。走反代时可以把 `web_host` 改成
`127.0.0.1`，不再对外直接暴露端口（安全组也不用放行 8766，只放行 443）。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/课表网页` | 回复网页版帮助链接（别名 `/课表帮助网页`、`/课表链接`） |

## 安全与隐私

- 本站**只展示帮助文档**，不提供任何课表数据端点；课表数据始终只保存在机器人本地
- 帮助文档跟随主插件版本：直接读取主插件 `docs/help.md`（文件变动自动刷新），
  找不到主插件时退回本插件自带的副本
- 建议走 HTTPS 反代对外提供；直接用 `http://IP:端口` 时内容明文传输（帮助文档无敏感信息）

## 相关仓库

- 主插件：[astrbot_plugin_schedule_lite](https://github.com/suiren0219/astrbot_plugin_schedule_lite)
