import os
import time
import requests
from seleniumbase import Driver

def send_tg_notification(photo_path, message):
    """发送带图片的 Telegram 图文通知"""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("MY_CHAT_ID")
    url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
    
    try:
        with open(photo_path, 'rb') as photo:
            payload = {
                'chat_id': tg_chat_id,
                'caption': message,
                'parse_mode': 'Markdown'
            }
            files = {'photo': photo}
            requests.post(url, data=payload, files=files)
    except Exception as e:
        print(f"发送通知失败: {e}")

def run_checkin(username, password):
    driver = Driver(uc=True, headless=True)
    driver.set_page_load_timeout(30) 
    screenshot_path = f"result_{username[:3]}.png"
    
    try:
        print(f"🚀 正在访问登录页: {username}")
        driver.get("https://api.dabo.im/login")
        time.sleep(15) 
        
        # --- 1. 智能登录点击 ---
        print("🔑 尝试触发登录按钮...")
        driver.wait_for_element('button', timeout=20)
        driver.execute_script("""
            let target = Array.from(document.querySelectorAll('span, button')).find(el => 
                el.textContent.includes('Sign in with Email') || 
                el.textContent.includes('使用邮箱') ||
                el.textContent.includes('用户名登录') ||
                el.textContent.trim() === 'Sign in' ||
                el.textContent.trim() === '登录'
            );
            if (target) {
                let btn = target.closest('button') || (target.tagName === 'BUTTON' ? target : null);
                if (btn) { btn.click(); btn.dispatchEvent(new Event('click', {bubbles: true})); }
            }
        """)
        time.sleep(8)
        
        # --- 2. 输入账号密码 ---
        print("⌨️ 正在输入凭据...")
        driver.wait_for_element("#username", timeout=25)
        driver.type('#username', username)
        driver.type('#password', password)
        
        driver.execute_script("""
            let submitBtn = document.querySelector('button[type="submit"]') || 
                            Array.from(document.querySelectorAll('span, button')).find(el => 
                                el.textContent.includes('Continue') || 
                                el.textContent.includes('继续') ||
                                el.textContent.trim() === 'Sign in' ||
                                el.textContent.trim() === '登录'
                            )?.closest('button');
            if (submitBtn) { submitBtn.click(); submitBtn.dispatchEvent(new Event('click', {bubbles: true})); }
        """)
        
        # --- 3. 登录后缓冲与导航 (精准定位个人设置) ---
        print("⚙️ 登录成功，正在进入个人设置页面...")
        time.sleep(15) 
        
        driver.execute_script("""
            let menus = Array.from(document.querySelectorAll('a, span, div, li'));
            let target = menus.find(el => {
                let txt = el.textContent.trim();
                return txt === '个人设置' || txt === 'Personal Settings';
            });
            if (target) {
                let clickable = target.closest('a') || target;
                clickable.click();
            }
        """)
        time.sleep(8)
        
        # --- 4. 视觉级智能提取余额 ---
        print("🔍 正在通过视觉字号抓取账户余额...")
        get_balance_js = """
            let elements = document.querySelectorAll('*');
            let bestBalance = '$0.00';
            let maxFontSize = 0;

            for (let el of elements) {
                let text = el.textContent.trim();
                if (/^\\$\\s*[0-9,]+(\\.[0-9]+)?$/.test(text)) {
                    let size = parseFloat(window.getComputedStyle(el).fontSize) || 0;
                    if (size > maxFontSize) {
                        maxFontSize = size;
                        bestBalance = text.replace(/\\s+/g, ''); 
                    }
                }
            }
            
            if (bestBalance === '$0.00') {
                let match = document.body.innerText.match(/(?:当前余额|可用额度)[:：\\s]*(\\$[0-9,]+\\.\\d+)/);
                if (match) bestBalance = match[1];
            }
            
            return bestBalance;
        """
        
        pre_balance_raw = driver.execute_script(get_balance_js)
        try:
            pre_balance_val = float(pre_balance_raw.replace('$', '').replace(',', '').strip())
        except:
            pre_balance_val = 0.0
            pre_balance_raw = "$0.00"
            
        print(f"💰 抓取到的主余额为: {pre_balance_raw}")
        
        # --- 5. 智能触发签到 (修复错点标题问题) ---
        print("⏳ 准备查找并点击签到按钮...")
        
        checkin_success = driver.execute_script("""
            // 策略1：优先寻找真正的 <button> 标签
            let buttons = Array.from(document.querySelectorAll('button'));
            let targetBtn = buttons.find(b => 
                (b.textContent.includes('立即签到') || b.textContent.includes('签到') || b.textContent.includes('Check in')) && 
                b.offsetParent !== null
            );

            // 策略2：有些UI用a或span做按钮，严格限制文本长度以防点到说明段落
            if (!targetBtn) {
                let els = Array.from(document.querySelectorAll('a, span, div'));
                targetBtn = els.find(e => {
                    let txt = e.textContent.trim();
                    return (txt === '立即签到' || txt === 'Check in now') && e.offsetParent !== null;
                });
            }

            if (targetBtn) {
                let clickable = targetBtn.closest('button') || targetBtn.closest('a') || targetBtn;
                clickable.click();
                clickable.dispatchEvent(new Event('click', {bubbles: true}));
                return true;
            }
            return false;
        """)
        
        status = "今日已签/未找到按钮 ℹ️"
        checkin_reward = "$0.00"
        
        if checkin_success:
            print("✅ 签到按钮已点击，等待 8 秒后刷新获取最新数据...")
            time.sleep(8)
            driver.refresh()
            time.sleep(10) 
            
            post_balance_raw = driver.execute_script(get_balance_js)
            try:
                post_balance_val = float(post_balance_raw.replace('$', '').replace(',', '').strip())
            except:
                post_balance_val = 0.0
                
            reward_val = post_balance_val - pre_balance_val
            if reward_val > 0:
                checkin_reward = f"${reward_val:.4f}"
                status = "续期成功 ✅"
            else:
                status = "今日已签 ℹ️"
        else:
            post_balance_raw = pre_balance_raw
            post_balance_val = pre_balance_val
            print("⚠️ 页面上没有找到签到按钮，可能在右上角隐藏或今日已签。")
        
        # --- 6. 截图并发送 ---
        driver.save_screenshot(screenshot_path)
        bj_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8*3600))
        
        msg = (
            f"✅ **LXCloud 自动化续期报告**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **账户：** `{username}`\n"
            f"🛰 **状态：** {status}\n"
            f"💰 **签到前：** `{pre_balance_raw}`\n"
            f"🎁 **获得：** `{checkin_reward}`\n"
            f"💵 **当前余额：** `{post_balance_raw}`\n"
            f"🕒 **北京时间：** `{bj_time}`\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        send_tg_notification(screenshot_path, msg)
        print(f"✨ {username} 处理完成")

    except Exception as e:
        driver.save_screenshot(f"error_{username[:3]}.png")
        send_tg_notification(f"error_{username[:3]}.png", f"❌ {username} 运行失败\n原因: 流程异常阻断")
        print(f"❌ {username} 报错: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    accounts_str = os.environ.get("LX_ACCOUNTS", "")
    if accounts_str:
        for item in accounts_str.split(","):
            if ":" in item:
                u, p = item.split(":", 1)
                run_checkin(u.strip(), p.strip())
