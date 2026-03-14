# dabohub-auto-checkin
需要填写的 3 个环境变量：
1. TELEGRAM_BOT_TOKEN
用途：你的 Telegram 机器人令牌，用于发送通知。
如何获取：在 Telegram 中搜索 @BotFather，创建一个新机器人（/newbot），成功后它会给你一串 Token。
格式示例：1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ
2. MY_CHAT_ID
用途：接收通知的 Telegram 账号 ID（你自己的 ID 或频道的 ID）。
如何获取：在 Telegram 中向 @userinfobot 或 @getmyid_bot 发送消息，它会回复你的 ID。
格式示例：123456789 （一串纯数字）
3. LX_ACCOUNTS
用途：你要自动签到的网站账号和密码。
格式要求：必须是 账号:密码 的格式。如果是多个账号，用英文逗号 , 隔开。
格式示例：
单账号：myemail@gmail.com:mypassword123
多账号：user1@gmail.com:pass1,user2@gmail.com:pass2
