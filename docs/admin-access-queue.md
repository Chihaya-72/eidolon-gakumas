# 管理员、密码访问与服务排队

部署的首位注册用户自动成为管理员。升级已有数据库时，最早注册的用户会获得持久管理员身份，迁移只执行一次。`EIDOLON_ADMINS` 仍可指定额外管理员；开发登录也只自动授权首位用户。管理员在设置「登录与数据」进入后台，在配置的「访问控制」中管理密码访问和访问黑名单，公用 API 在配置的第一个标签「公用 API」。

## 网站访问密码

默认关闭，开启前设置 8 至 128 个字符的密码。访客在登录前输入，已登录用户也需要通行凭据。门禁保护页面和业务 API；`public/` 里的图片、声音和字体等静态文件不经过门禁，后端 5 秒内未答复时页面返回 503。密码只保存加盐 scrypt 哈希，不回显。通行 Cookie 为 HttpOnly，有效期 30 天；开启、关闭或修改密码会撤销旧凭据，保存配置的管理员自动获得新凭据。

浏览器和 IP 分别累计失败次数，任一达到三次便永久封禁本次浏览器及 IP；成功验证清零对应失败次数。共用 IP 的其他人也会被拦截。访问黑名单与账号封禁相互独立，关闭门禁不删除黑名单，重新开启后继续生效。后台按封禁事件解封，界面显示匿名标识。

生产部署需使用更新后的 `deploy/Caddyfile`：Caddy 覆写 `X-Eidolon-Client-IP`，Next.js 转发，后端仅接受来自本机受控代理的这个头。前后端生产监听地址保持 `127.0.0.1`。自己使用其他反向代理时也必须覆写这个头，不能透传客户端传入值。

### 使用 Cloudflare CDN

自带 Caddyfile 已配置 Cloudflare 官方 IPv4、IPv6 回源网段为可信代理，仅从这些连接的 `CF-Connecting-IP` 解析访客 IP，再用 `{client_ip}` 覆写 `X-Eidolon-Client-IP`。直连源站时仍使用连接 IP，不能靠伪造请求头改变封禁对象。这个配置适用于 Cloudflare 橙云直接回源 Caddy；使用 Cloudflare Tunnel 或前面还有其他代理时，需要另行配置可信代理链。

Cloudflare 必须保留访客 IP 请求头：不要启用 **Remove visitor IP headers**；**Pseudo IPv4** 使用 Off 或 Add Header，避免 Overwrite Headers 把真实 IPv6 替换为合成 IPv4。CF 调整回源网段后，按 [IPv4 列表](https://www.cloudflare.com/ips-v4/)和 [IPv6 列表](https://www.cloudflare.com/ips-v6/)同步更新 Caddyfile（当前核对日期：2026-11-05）。解析规则见 [Caddy 可信代理文档](https://caddyserver.com/docs/caddyfile/options#trusted_proxies)，请求头行为见 [Cloudflare 文档](https://developers.cloudflare.com/fundamentals/reference/http-headers/)。

把更新后的 `deploy/Caddyfile` 同步到服务器后，先校验再重载：

```sh
docker compose -f docker-compose.prod.yml exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

旧配置使用 `{remote_host}` 时，可能已经按 CF 节点 IP 累计错误次数或产生误封。修正配置不会自动删除这些记录；误封可在后台访问黑名单中解除，进不了后台时使用下面的恢复命令。

无法进入后台时，在服务器中恢复（`--db` 可指定数据库）：

```sh
# Docker：替换为当前使用的 compose 文件
docker compose -f docker-compose.prod.yml exec backend eidolon access disable
docker compose -f docker-compose.prod.yml exec backend eidolon access unban
# 本地：关闭门禁 / 解除某次封禁 / 解除全部封禁
eidolon --db /path/to/eidolon.db access disable
eidolon --db /path/to/eidolon.db access unban <封禁编号>
eidolon --db /path/to/eidolon.db access unban
```

命令只修改数据库，正在运行的服务随下个请求读取新状态。已删除首位管理员不会自动把后来注册的人提升为管理员，需要用 `EIDOLON_ADMINS` 恢复管理入口。

## 服务队列

当前采用单后端进程，一个共享服务位。文字回复、整通语音、酒吧每次生成回复、朗读及异步生图进入同一队列；后台同步和探活等维护工作不参与。

排序按「管理员优先 → 注册用户先于游客 → 最近滚动六小时使用次数较少者优先 → 入队先后」。每次调度重新计算，因此新来的低使用量用户能插到等待任务前；已经开始的任务不会被打断，管理员也要等当前操作结束。

通过校验并开始服务时计一次。排队等待、等待中取消或被拒绝不计；开始后的上游失败仍计。浏览器票据轮到后过期或被放弃也计一次，因为它已经占过唯一的服务位。每位用户最多同时持有 5 张等待中或已轮到的浏览器票据，超出时返回 429。计数独立于每小时限额，写入 SQLite，重启后保留。六小时前恰好到期的记录不参与排序。

主要 API 全部自带则免排队、免队列计数：文字和酒吧看 LLM；语音看 LLM、语音识别、语音合成；朗读看合成；生图看生图密钥。混用本站主要 API 则排队，判断、检索等辅助服务不影响此规则；原来的限额规则继续生效。

语音从开始服务到通话结束占位。酒吧每次回复结束后释放，等待调酒不占位。异步照片独立排队，父文字回合不等待照片生成，以免死锁；使用自带生图的照片无需等待共享服务位。

前端每两秒刷新位置并提供取消按钮，轮到语音后才打开麦克风。排队期间 60 秒未续约则过期；轮到后保留 15 秒，未开始便释放。重启后待执行票据失效，需要重新排队，未提交的文字会保留供重试。

接口：`GET /api/access/status`、`POST /api/access/verify`；管理员 `GET/PUT /api/admin/access`、`GET /api/admin/access/bans`、`DELETE /api/admin/access/bans/{id}`。队列使用 `POST /api/queue`、`GET/DELETE /api/queue/{id}`，原操作携带 `X-Queue-Ticket`。语音票据同时绑定对话 ID；票据不包含密钥，实际业务请求重新核验密钥归属。直接调用原业务接口也会排队。

## 游客登录

设置 `EIDOLON_GUEST_LOGIN=1` 后，登录面板提供游客登录。每个浏览器拥有独立游客身份，退出后同一浏览器可再次进入；清除 Cookie 后不能找回原身份。游客仍需确认隐私政策、条款与年龄声明，不会参与首位管理员授权。访问密码同样保护游客登录接口。

游客用量在后台「限额与玩法」的「游客用量」卡里设置，0 表示不开放。每位游客有自己的每小时限额，所有游客合计还有一个总量（回合、通话、照片、光顾、朗读各算一次），每个 IP 每小时能产生的新游客数也有上限，因此清除 Cookie 换身份绕不过总量。默认每位游客每小时 10 回合、3 次朗读，通话、照片和光顾不开放，合计 100 次，每个 IP 每小时 3 个新游客。自带密钥且符合免限额规则的使用不计入。排队时游客排在所有注册用户之后。

设置 `EIDOLON_PASSWORD_LOGIN=1` 后，登录面板提供名称和密码的注册、登录。第一个在名称后面加 `+admin` 注册的人成为管理员，后缀不进入名称，以后用不带后缀的名称登录。这条规则是公开的，打开后请立刻注册占下这个资格；普通的密码用户不会因为排在第一个成为管理员。密码目前不能自助重置。

后台「限额与玩法」的「自行填写 API」开关决定用户能否使用自己的 API。关闭后服务器忽略请求带来的密钥，不再连接用户写的地址。
