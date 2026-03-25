import os
import time
import requests
import subprocess
from PIL import Image
from seleniumbase import Driver
from concurrent.futures import ThreadPoolExecutor

EXPAND_POPUP_JS = """
(function() {
    var turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (turnstileInput) {
        var el = turnstileInput;
        for (var i = 0; i < 20; i++) {
            el = el.parentElement;
            if (!el) break;
            var style = window.getComputedStyle(el);
            if (style.overflow === 'hidden' || style.overflowX === 'hidden' || style.overflowY === 'hidden') {
                el.style.overflow = 'visible';
            }
            el.style.minWidth = 'max-content';
        }
    }
    var iframes = document.querySelectorAll('iframe');
    iframes.forEach(function(iframe) {
        iframe.style.visibility = 'visible';
        iframe.style.opacity = '1';
    });
})();
"""

def get_turnstile_coords(driver):
    return driver.execute_script("""
        var getC = function(rect) {
            var chromeBarHeight = window.outerHeight - window.innerHeight;
            return {
                x: Math.round(rect.x + 30) + (window.screenX || 0),
                y: Math.round(rect.y + rect.height / 2) + (window.screenY || 0) + chromeBarHeight
            };
        };
        var iframes = document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            var src = iframes[i].src || '';
            if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
                var rect = iframes[i].getBoundingClientRect();
                if (rect.width > 30 && rect.height > 20) return getC(rect);
            }
        }
        var input = document.querySelector('input[name="cf-turnstile-response"]');
        if (input) {
            var container = input.parentElement;
            for (var j = 0; j < 5; j++) {
                if (!container) break;
                var rect = container.getBoundingClientRect();
                if (rect.width > 80 && rect.height > 20) return getC(rect);
                container = container.parentElement;
            }
        }
        return null;
    """)

def has_turnstile_challenge(driver):
    return driver.execute_script("""
        var hasIframe = Array.from(document.querySelectorAll('iframe')).some(function(frame) {
            var src = (frame.src || '').toLowerCase();
            return src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges');
        });
        var hasInput = !!document.querySelector("input[name='cf-turnstile-response']");
        return hasIframe || hasInput;
    """)

def os_hardware_click(x, y):
    try:
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "chrome"], capture_output=True, text=True)
        w_ids = result.stdout.strip().split('\n')
        if w_ids and w_ids[0]:
            subprocess.run(["xdotool", "windowactivate", w_ids[0]], stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        os.system(f"xdotool mousemove {int(x)} {int(y)} click 1")
        print(f"👆 已使用 xdotool 物理点击屏幕坐标 ({x}, {y})")
        return True
    except Exception as e:
        print(f"⚠️ xdotool 点击失败: {e}")
        return False

def send_tg_notification(photo_path, message):
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("MY_CHAT_ID")
    
    sent_success = False
    
    if photo_path and os.path.exists(photo_path):
        url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
        try:
            print(f"📤 正在上传汇总报告图片 ({os.path.getsize(photo_path)/1024:.1f} KB)...")
            with open(photo_path, 'rb') as photo:
                payload = {'chat_id': tg_chat_id, 'caption': message, 'parse_mode': 'Markdown'}
                files = {'photo': photo}
                resp = requests.post(url, data=payload, files=files, timeout=60)
                if resp.status_code == 200:
                    print("✅ Telegram 图片报告发送成功")
                    sent_success = True
                else:
                    print(f"❌ TG 图片发送失败，状态码: {resp.status_code}, 原因: {resp.text}")
        except Exception as e:
            print(f"❌ 发送图片过程发生异常: {e}")

    if not sent_success:
        print("⚠️ 尝试补发纯文字通知...")
        text_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        try:
            resp = requests.post(text_url, data={'chat_id': tg_chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=30)
            if resp.status_code == 200:
                print("✅ Telegram 纯文字通知发送成功")
        except Exception as e:
            print(f"❌ 发送文字通知发生异常: {e}")

def run_checkin(username, password):
    print(f"🔧 正在初始化带 UI 窗口的浏览器: {username} ...")
    driver = Driver(uc=True, headless=False, chromium_arg="--disable-dev-shm-usage,--no-sandbox,--window-size=1920,1080")
    driver.set_window_rect(0, 0, 1920, 1080) 
    driver.set_page_load_timeout(30) 
    screenshot_path = f"result_{username}.png"
    
    result_data = {
        "username": username,
        "status": "运行失败 ❌",
        "pre": "$0.00",
        "reward": "$0.00",
        "post": "$0.00",
        "screenshot": None
    }
    
    try:
        print(f"🚀 正在访问登录页: {username}")
        driver.get("https://api.dabo.im/login")
        time.sleep(15) 
        
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
        
        print("⌨️ 正在输入凭据...")
        driver.wait_for_element("#username", timeout=25)
        driver.type('#username', username)
        driver.type('#password', password)
        
        print("🛡️ 开始扫描并处理可能存在的 Cloudflare 验证框...")
        time.sleep(4)
        driver.execute_script(EXPAND_POPUP_JS)
        time.sleep(1)

        cf_detected = False
        for probe in range(3):
            if has_turnstile_challenge(driver):
                cf_detected = True
                break
            if probe < 2:
                time.sleep(2)

        if not cf_detected:
            print("INFO: No Cloudflare challenge detected, continue login directly.")

        for attempt in (range(5) if cf_detected else []):
            driver.execute_script("""
                var frames = document.querySelectorAll('iframe');
                for (var i = 0; i < frames.length; i++) {
                    if (frames[i].src.includes('cloudflare') || frames[i].src.includes('turnstile')) {
                        frames[i].scrollIntoView({block: 'center'});
                        break;
                    }
                }
            """)
            time.sleep(1)

            is_done = driver.execute_script("var cf = document.querySelector(\"input[name='cf-turnstile-response']\"); return cf && cf.value.length > 20;")
            if is_done:
                print("✅ CF 盾底层验证已通过！等待前端状态同步...")
                time.sleep(3)  
                break
            
            print(f"🖱️ 尝试寻找并物理点击过盾 (第 {attempt + 1} 次)...")
            if attempt > 0 and not has_turnstile_challenge(driver):
                print("INFO: Cloudflare challenge not detected now, skip remaining attempts.")
                break

            coords = get_turnstile_coords(driver)
            if coords:
                os_hardware_click(coords['x'], coords['y'])
                print("⏳ 等待盾验证动画 (5秒)...")
                time.sleep(5)
            else:
                print("⚠️ 暂未发现盾的位置，等待页面继续加载...")
                time.sleep(4) 
        
        print("📤 提交登录...")
        time.sleep(1) 
        try:
            driver.click('button[type="submit"]')
            print("✅ 已使用原生点击提交表单")
        except:
            print("⚠️ 原生点击失败，降级使用 JS 点击...")
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
        
        print("⏳ 等待页面跳转校验...")
        time.sleep(8)
        if "login" in driver.current_url or "auth" in driver.current_url:
            raise Exception("登录失败：未能离开登录页面，可能是被 CF 盾拦截或网络卡顿")

        print("⚙️ 登录成功，正在进入个人设置页面...")
        time.sleep(10) 
        
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
            
        print(f"💰 {username} 抓取到的主余额为: {pre_balance_raw}")
        
        print("⏳ 准备查找并点击签到按钮...")
        checkin_success = driver.execute_script("""
            let buttons = Array.from(document.querySelectorAll('button'));
            let targetBtn = buttons.find(b => 
                (b.textContent.includes('立即签到') || b.textContent.includes('签到') || b.textContent.includes('Check in')) && 
                b.offsetParent !== null
            );
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
        post_balance_raw = pre_balance_raw
        
        if checkin_success:
            print(f"✅ {username} 签到按钮已点击，等待 8 秒后刷新获取最新数据...")
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
                status = "签到成功 ✅"
            else:
                status = "今日已签 ℹ️"
        else:
            print(f"⚠️ {username} 页面上没有找到签到按钮。")

        driver.save_screenshot(screenshot_path)
        result_data.update({
            "status": status,
            "pre": pre_balance_raw,
            "reward": checkin_reward,
            "post": post_balance_raw,
            "screenshot": screenshot_path
        })
        print(f"✨ {username} 处理完成")

    except Exception as e:
        error_screenshot = f"error_{username}.png"
        try: driver.save_screenshot(error_screenshot)
        except: pass
        result_data["screenshot"] = error_screenshot
        print(f"❌ {username} 报错: {e}")
    finally:
        try: driver.quit()
        except: pass
        return result_data

if __name__ == "__main__":
    accounts_str = os.environ.get("LX_ACCOUNTS", "")
    if accounts_str:
        tasks = []
        for item in accounts_str.split(","):
            if ":" in item:
                u, p = item.split(":", 1)
                tasks.append((u.strip(), p.strip()))
        
        print("🔧 正在初始化环境，请稍候...")
        try:
            temp_driver = Driver(uc=True, headless=True)
            temp_driver.quit()
            time.sleep(2) 
        except Exception as e:
            pass

        max_workers = 1 
        all_results = []
        
        print(f"🚀 排队模式启动 | 账号总数: {len(tasks)} | 最大并发: {max_workers}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            def safe_run(p):
                return run_checkin(*p)
                
            all_results = list(executor.map(safe_run, tasks))

        valid_screenshots = [r['screenshot'] for r in all_results if r['screenshot'] and os.path.exists(r['screenshot'])]
        final_photo = "final_combined_report.png"
        
        if valid_screenshots:
            imgs = [Image.open(s) for s in valid_screenshots]
            num_imgs = len(imgs)
            cols = 2  
            rows = (num_imgs + 1) // cols  
            
            single_w, single_h = imgs[0].size
            combined_img = Image.new('RGB', (single_w * cols, single_h * rows), (255, 255, 255))
            
            for index, im in enumerate(imgs):
                row_idx = index // cols
                col_idx = index % cols
                x_offset = col_idx * single_w
                y_offset = row_idx * single_h
                combined_img.paste(im, (x_offset, y_offset))
            
            combined_img.save(final_photo)

        bj_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8*3600))
        
        report_msg = [
            f"✨ **DaBoBo 自动签到任务汇总** ✨",
            f"📅 运行日期：`{bj_time.split(' ')[0]}`",
            f"🕒 结束时间：`{bj_time.split(' ')[1]}`",
            f"━━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        for r in all_results:
            status_icon = "✅" if "成功" in r['status'] else "ℹ️" if "已签" in r['status'] else "❌"
            safe_username = r['username'].replace('_', '\\_')
            
            report_msg.append(
                f"👤 **用户账号** | `{safe_username}`\n"
                f"📊 **签到状态** | {status_icon} {r['status']}\n"
                f"💰 **余额变动** | `{r['pre']}` → `{r['post']}`\n"
                f"🎁 **本次奖励** | `+{r['reward']}`\n"
                f"──────────────────────"
            )
        
        success_count = sum(1 for r in all_results if "成功" in r['status'] or "已签" in r['status'])
        report_msg.append(f"📢 统计：已处理 `{len(all_results)}` 个账号，正常 `{success_count}` 个。")
        
        full_message = "\n".join(report_msg)
        send_tg_notification(final_photo if os.path.exists(final_photo) else None, full_message)

    print("📢 所有任务处理完毕并已发送汇总通知。")
