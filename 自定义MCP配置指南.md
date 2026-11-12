# WorkBuddy 自定义 MCP 配置指南

> 对应小红书《Personal Agent 七种邪修用法》里的「分水岭玩法」：厂商生态接得再多也有边界，**自定义 MCP 之后，边界取决于你自己**——让 AI 穿透公域 SaaS 与你的本地私有环境（笔记库、NAS、智能家居、内部 API）。
>
> 官方文档：[workbuddy.cn/docs/cli/mcp](https://www.workbuddy.cn/docs/cli/mcp) · [开放平台连接器规范](https://open.workbuddy.cn/docs/connector)

---

## 一、三种配置入口（任选其一）

| 入口 | 路径 | 适合 |
|---|---|---|
| 连接器页 | 侧边栏「专家·技能·连接器」→ 连接器页签 → 右上角**自定义连接器** | 图形化操作，最简单 |
| MCP 管理页 | 侧边栏 **插件 → MCP 服务器 → 配置 MCP** | 管理多个 server、看状态灯 |
| 直接改配置文件 | 见下方「配置文件位置」 | 团队共享、批量部署 |

## 二、配置文件位置（两级作用域）

```
~/.workbuddy/mcp.json          ← 用户级：配一次，全局所有任务可用
<项目目录>/.workbuddy/mcp.json  ← 项目级：仅当前项目生效，互不干扰
```

## 三、配置格式（三种传输类型）

### 1. stdio —— 本地进程（最常用：接本地工具/脚本）

```json
{
  "mcpServers": {
    "my-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/my_mcp_server.py"],
      "env": { "API_KEY": "${API_KEY}" }
    }
  }
}
```

### 2. http —— 远程服务（接云端 API、NAS 服务）

```json
{
  "mcpServers": {
    "remote-service": {
      "type": "http",
      "url": "https://api.example.com/mcp",
      "headers": { "Authorization": "Bearer ${MY_API_TOKEN}" }
    }
  }
}
```

### 3. sse —— Server-Sent Events（老版本远程服务）

```json
{
  "mcpServers": {
    "legacy-service": {
      "type": "sse",
      "url": "https://api.example.com/mcp/sse",
      "headers": { "x-api-key": "sk-xxxxx" }
    }
  }
}
```

**环境变量语法**：`${VAR:-默认值}`——未设置时用默认值，避免密钥硬编码：

```json
"command": "${PYTHON_PATH:-python}"
```

## 四、实战示例（三个高频场景）

### 场景 1：接入 Obsidian 笔记库

前置：Obsidian 安装社区插件 **Local REST API**（设置 → 第三方插件 → 浏览 → 搜索安装 → 启用并复制 API Key）。

```json
{
  "mcpServers": {
    "obsidian": {
      "type": "http",
      "url": "https://127.0.0.1:27124/",
      "headers": { "Authorization": "Bearer ${OBSIDIAN_REST_KEY}" }
    }
  }
}
```

配好后直接对 WorkBuddy 说：「帮我把本周会议记录整理进我的 Obsidian 笔记库」。
（具体实现包名以社区项目 README 为准，stdio 方案可用 `npx` 拉起对应的 obsidian-mcp 实现。）

### 场景 2：接入 Home Assistant 智能家居

```json
{
  "mcpServers": {
    "homeassistant": {
      "type": "http",
      "url": "http://<NAS或树莓派IP>:8123/mcp",
      "headers": { "Authorization": "Bearer ${HA_TOKEN}" }
    }
  }
}
```

`HA_TOKEN` 在 Home Assistant → 用户头像 → 安全 → 长期访问令牌里生成。
配好后可以说：「回家模式：打开客厅灯、把空调调到 26 度」。

### 场景 3：接入 NAS / 私有 API

任何提供 MCP 端点的自建服务（群晖、内部工具网关）都用 **http 类型**模板；自写脚本用 **stdio 类型**模板。开发自建 MCP Server 参考 [open.workbuddy.cn/docs/connector](https://open.workbuddy.cn/docs/connector)（Python/Node SDK、OAuth 鉴权、SLA ≥ 99.9% 建议值）。

## 五、验证与排障

| 现象 | 处理 |
|---|---|
| 配置后没反应 | 看管理页**状态灯**：绿色=可用，红色=配置有误 |
| 提示 Missing environment variables | 用 `/mcp` 命令查看诊断，列出所有缺失的环境变量 |
| 环境变量展开结果不确定 | 同样用 `/mcp` 查看展开后的实际配置 |
| stdio 起不来 | 先在终端手动执行 `command + args` 确认脚本能独立运行 |
| HTTP 连不上 | `curl -v <url>` 先通网络，再查 Token 是否过期 |

## 六、安全守则（必读）

1. **密钥放环境变量，不要明文写进 mcp.json**；公共设备尤其注意；
2. MCP 以**你的身份**操作外部系统——涉及对外发送、内容修改，执行前再确认一次目标对象；
3. 第三方 MCP Server 先审来源再接入，最小授权、按需启用；
4. Token 泄露第一时间在对应平台吊销重发。

---

*生成于 2026-11-11 · 由 WorkBuddy 整理*
