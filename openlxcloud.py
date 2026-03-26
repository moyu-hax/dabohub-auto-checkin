import os
import time
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from seleniumbase import Driver

LOGIN_URL = "https://api.dabo.im/login"

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


def parse_amount(text):
    try:
        return float(str(text).replace('$', '').replace(',', '').strip())
    except Exception:
        return 0.0


def has_turnstile_challenge(driver):
    return driver.execute_script("""
        var hasIframe = Array.from(document.querySelectorAll('iframe')).some(function(frame) {
            var src = (frame.src || '').toLowerCase();
            return src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges');
        });
        var hasInput = !!document.querySelector("input[name='cf-turnstile-response']");
        return hasIframe || hasInput;
    """)


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
            var src = (iframes[i].src || '').toLowerCase();
            if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
                var rect = iframes[i].getBoundingClientRect();
                if (rect.width > 30 && rect.height > 20) return getC(rect);
            }
        }

        var input = document.querySelector("input[name='cf-turnstile-response']");
        if (input) {
            var container = input.parentElement;
            for (var j = 0; j < 6; j++) {
                if (!container) break;
                var r = container.getBoundingClientRect();
                if (r.width > 80 && r.height > 20) return getC(r);
                container = container.parentElement;
            }
        }
        return null;
    """)


def os_hardware_click(x, y):
    try:
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", "chrome"],
            capture_output=True,
            text=True,
            timeout=8,
        )
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


def click_email_login_entry(driver):
    return driver.execute_script("""
        var normalize = function(s) {
            return (s || '').replace(/\s+/g, '').toLowerCase();
        };

        var keywords = [
            'sign in with email',
            'use email or username',
            'continue with email',
            '使用邮箱或用户名登录',
            '使用邮箱登录',
            '邮箱登录',
            '用户名登录',
            '邮箱或用户名'
        ].map(normalize);

        var nodes = Array.from(document.querySelectorAll('button, a, span, div'));
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el || !el.textContent) continue;
            var txt = normalize(el.textContent);
            if (!txt) continue;
            var matched = keywords.some(function(k) { return txt.includes(k); });
            if (!matched) continue;
            var clickable = el.closest('button, a') || el;
            clickable.click();
            clickable.dispatchEvent(new Event('click', {bubbles: true}));
            return true;
        }
        return false;
    """)


def credentials_form_ready(driver):
    return driver.execute_script(
        "return !!document.querySelector('#username') && !!document.querySelector('#password');"
    )


def submit_login_form(driver):
    try:
        driver.click('button[type="submit"]')
        return True
    except Exception:
        return driver.execute_script("""
            var submitBtn = document.querySelector('button[type="submit"]') ||
                            Array.from(document.querySelectorAll('button, a, span, div')).find(function(el) {
                                var t = (el.textContent || '').trim();
                                return t.includes('Continue') ||
                                       t.includes('Sign in') ||
                                       t.includes('继续') ||
                                       t.includes('登录');
                            })?.closest('button, a');
            if (submitBtn) {
                submitBtn.click();
                submitBtn.dispatchEvent(new Event('click', {bubbles: true}));
                return true;
            }
            return false;
        """)


def get_login_state(driver):
    return driver.execute_script("""
        var url = (window.location.href || '').toLowerCase();
        var hasUsername = !!document.querySelector('#username, input[name="username"], input[type="email"]');
        var hasPassword = !!document.querySelector('#password, input[name="password"], input[type="password"]');
        var onLoginForm = hasUsername && hasPassword;
        var onLoginRoute = url.includes('/login') || url.includes('/auth');
        var body = document.body ? (document.body.innerText || '') : '';
        var hasPostLoginHint = body.includes('个人设置') || body.includes('Personal Settings') || body.includes('Check in');
        var loggedIn = hasPostLoginHint || (!onLoginForm && !onLoginRoute);
        return {
            on_login_form: onLoginForm,
            on_login_route: onLoginRoute,
            has_post_login_hint: hasPostLoginHint,
            logged_in: loggedIn
        };
    """)


def get_login_error_hint(driver):
    return driver.execute_script("""
        var text = document.body ? (document.body.innerText || '') : '';
        var lower = text.toLowerCase();
        var hints = [
            '密码错误', '用户名或密码错误', '验证码', '网络',
            'invalid', 'incorrect', 'too many requests', 'rate limit', 'verification', 'network'
        ];
        for (var i = 0; i < hints.length; i++) {
            if (lower.includes(String(hints[i]).toLowerCase())) return hints[i];
        }
        return '';
    """)


def send_tg_notification(photo_path, message):
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("MY_CHAT_ID")

    if not tg_token or not tg_chat_id:
        print("⚠️ 未配置 Telegram 参数，跳过发送通知")
        return

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
                print(f"❌ Telegram 图片发送失败: {resp.status_code} | {resp.text}")
        except Exception as e:
            print(f"❌ Telegram 图片发送异常: {e}")

    if not sent_success:
        try:
            text_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            resp = requests.post(
                text_url,
                data={'chat_id': tg_chat_id, 'text': message, 'parse_mode': 'Markdown'},
                timeout=30,
            )
            if resp.status_code == 200:
                print("✅ Telegram 文本通知发送成功")
            else:
                print(f"❌ Telegram 文本发送失败: {resp.status_code} | {resp.text}")
        except Exception as e:
            print(f"❌ Telegram 文本发送异常: {e}")


def run_checkin(username, password):
    print(f"🔧 正在初始化带 UI 窗口的浏览器: {username} ...")
    driver = Driver(
        uc=True,
        headless=False,
        chromium_arg="--disable-dev-shm-usage,--no-sandbox,--window-size=1920,1080",
    )
    driver.set_window_rect(0, 0, 1920, 1080)
    driver.set_page_load_timeout(35)

    screenshot_path = f"result_{username}.png"
    result_data = {
        "username": username,
        "status": "运行失败 ❌",
        "pre": "$0.00",
        "reward": "$0.00",
        "post": "$0.00",
        "screenshot": None,
    }

    try:
        print(f"🚀 正在访问登录页: {username}")
        driver.get(LOGIN_URL)
        time.sleep(12)

        print("🔑 尝试触发登录按钮...")
        driver.wait_for_element('button', timeout=25)
        clicked = click_email_login_entry(driver)
        if clicked:
            print("INFO: 已点击邮箱/用户名登录入口")
        else:
            print("INFO: 未找到入口按钮，直接等待输入框")

        for _ in range(3):
            if credentials_form_ready(driver):
                break
            click_email_login_entry(driver)
            time.sleep(2)

        print("⌨️ 正在输入凭据...")
        driver.wait_for_element("#username", timeout=30)
        driver.type('#username', username)
        driver.type('#password', password)

        print("🛡️ 开始扫描并处理可能存在的 Cloudflare 验证框...")
        time.sleep(2)
        driver.execute_script(EXPAND_POPUP_JS)
        time.sleep(1)

        cf_detected = False
        for probe in range(3):
            if has_turnstile_challenge(driver):
                cf_detected = True
                break
            if probe < 2:
                time.sleep(2)

        if cf_detected:
            for attempt in range(5):
                driver.execute_script("""
                    var frames = document.querySelectorAll('iframe');
                    for (var i = 0; i < frames.length; i++) {
                        var src = (frames[i].src || '').toLowerCase();
                        if (src.includes('cloudflare') || src.includes('turnstile')) {
                            frames[i].scrollIntoView({block: 'center'});
                            break;
                        }
                    }
                """)
                time.sleep(1)

                is_done = driver.execute_script(
                    "var cf=document.querySelector(\"input[name='cf-turnstile-response']\");"
                    "return !!(cf && cf.value && cf.value.length > 20);"
                )
                if is_done:
                    print("✅ CF 验证已通过")
                    time.sleep(2)
                    break

                if attempt > 0 and not has_turnstile_challenge(driver):
                    print("INFO: 当前页面已无 CF 验证，提前结束过盾尝试")
                    break

                print(f"🖱️ 尝试寻找并物理点击过盾 (第 {attempt + 1} 次)...")
                coords = get_turnstile_coords(driver)
                if coords:
                    os_hardware_click(coords['x'], coords['y'])
                    print("⏳ 等待盾验证动画 (5秒)...")
                    time.sleep(5)
                else:
                    print("⚠️ 未找到盾位置，继续等待页面变化")
                    time.sleep(3)
        else:
            print("INFO: 未检测到 Cloudflare 验证，直接继续登录")

        print("📤 提交登录...")
        time.sleep(1)
        if submit_login_form(driver):
            print("✅ 登录表单已提交")
        else:
            print("⚠️ 第一次未找到提交按钮")

        print("⏳ 等待页面跳转校验...")
        login_success = False
        for tick in range(20):
            state = get_login_state(driver)
            if state.get("logged_in"):
                login_success = True
                break
            if tick in (6, 12) and state.get("on_login_form"):
                print(f"INFO: 第 {tick + 1} 秒仍在登录表单，自动重提一次")
                submit_login_form(driver)
            time.sleep(1)

        if not login_success:
            hint = get_login_error_hint(driver)
            if hint:
                raise Exception(f"登录失败：仍停留在登录页，疑似提示: {hint}")
            raise Exception("登录失败：仍停留在登录页，可能网络波动/账号风控/页面卡顿")

        print("⚙️ 登录成功，正在进入个人设置页面...")
        time.sleep(8)
        driver.execute_script("""
            var menus = Array.from(document.querySelectorAll('a, span, div, li, button'));
            var target = menus.find(function(el) {
                var txt = (el.textContent || '').trim();
                return txt === '个人设置' || txt === 'Personal Settings';
            });
            if (target) {
                var clickable = target.closest('a, button') || target;
                clickable.click();
            }
        """)
        time.sleep(6)

        print("🔍 正在通过视觉字号抓取账户余额...")
        get_balance_js = """
            var elements = document.querySelectorAll('*');
            var bestBalance = '$0.00';
            var maxFontSize = 0;
            for (var i = 0; i < elements.length; i++) {
                var el = elements[i];
                var text = (el.textContent || '').trim();
                if (/^\$\s*[0-9,]+(\.[0-9]+)?$/.test(text)) {
                    var size = parseFloat(window.getComputedStyle(el).fontSize) || 0;
                    if (size > maxFontSize) {
                        maxFontSize = size;
                        bestBalance = text.replace(/\s+/g, '');
                    }
                }
            }
            if (bestBalance === '$0.00') {
                var m = (document.body.innerText || '').match(/(?:当前余额|可用额度)[:：\s]*(\$[0-9,]+\.[0-9]+)/);
                if (m) bestBalance = m[1];
            }
            return bestBalance;
        """

        pre_balance_raw = driver.execute_script(get_balance_js) or "$0.00"
        pre_balance_val = parse_amount(pre_balance_raw)
        print(f"💰 {username} 抓取到的主余额为: {pre_balance_raw}")

        print("⏳ 准备查找并点击签到按钮...")
        checkin_success = driver.execute_script("""
            var buttons = Array.from(document.querySelectorAll('button, a, span, div'));
            var target = buttons.find(function(el) {
                var txt = (el.textContent || '').trim();
                if (el.offsetParent === null) return false;
                return txt.includes('立即签到') || txt.includes('签到') ||
                       txt.includes('Check in') || txt.includes('Check in now');
            });
            if (!target) return false;
            var clickable = target.closest('button, a') || target;
            clickable.click();
            clickable.dispatchEvent(new Event('click', {bubbles: true}));
            return true;
        """)

        status = "今日已签/未找到签到按钮 ⚠️"
        post_balance_raw = pre_balance_raw
        reward_str = "$0.00"

        if checkin_success:
            print(f"✅ {username} 签到按钮已点击，等待 8 秒后刷新获取最新数据...")
            time.sleep(8)
            driver.refresh()
            time.sleep(8)
            post_balance_raw = driver.execute_script(get_balance_js) or pre_balance_raw
            post_balance_val = parse_amount(post_balance_raw)
            reward_val = post_balance_val - pre_balance_val
            if reward_val > 0:
                reward_str = f"${reward_val:.4f}"
                status = "签到成功 ✅"
            else:
                status = "今日已签 ⚠️"
        else:
            print(f"⚠️ {username} 页面上未找到签到按钮")

        driver.save_screenshot(screenshot_path)
        result_data.update(
            {
                "status": status,
                "pre": pre_balance_raw,
                "reward": reward_str,
                "post": post_balance_raw,
                "screenshot": screenshot_path,
            }
        )
        print(f"✨ {username} 处理完成")

    except Exception as e:
        error_screenshot = f"error_{username}.png"
        try:
            driver.save_screenshot(error_screenshot)
        except Exception:
            pass
        result_data["screenshot"] = error_screenshot if os.path.exists(error_screenshot) else None
        print(f"❌ {username} 报错: {e}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        return result_data


if __name__ == "__main__":
    accounts_str = os.environ.get("LX_ACCOUNTS", "")
    if not accounts_str:
        print("⚠️ 未配置 LX_ACCOUNTS，任务结束")
        raise SystemExit(0)

    tasks = []
    for item in accounts_str.split(","):
        if ":" in item:
            u, p = item.split(":", 1)
            u, p = u.strip(), p.strip()
            if u and p:
                tasks.append((u, p))

    if not tasks:
        print("⚠️ LX_ACCOUNTS 格式无有效账号，任务结束")
        raise SystemExit(0)

    print("🔧 正在初始化环境，请稍候...")
    try:
        temp_driver = Driver(uc=True, headless=True)
        temp_driver.quit()
        time.sleep(2)
    except Exception:
        pass

    max_workers = 1
    print(f"🚀 排队模式启动 | 账号总数: {len(tasks)} | 最大并发: {max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        all_results = list(executor.map(lambda p: run_checkin(*p), tasks))

    valid_screenshots = [r["screenshot"] for r in all_results if r.get("screenshot") and os.path.exists(r["screenshot"])]
    final_photo = "final_combined_report.png"

    if valid_screenshots:
        imgs = [Image.open(s) for s in valid_screenshots]
        cols = 2
        rows = (len(imgs) + cols - 1) // cols
        single_w, single_h = imgs[0].size
        combined_img = Image.new('RGB', (single_w * cols, single_h * rows), (255, 255, 255))
        for idx, im in enumerate(imgs):
            row_idx = idx // cols
            col_idx = idx % cols
            combined_img.paste(im, (col_idx * single_w, row_idx * single_h))
        combined_img.save(final_photo)

    bj_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8 * 3600))
    report_lines = [
        "✅ **DaBoBo 自动签到任务汇总** ✅",
        f"📅 运行日期: `{bj_time.split(' ')[0]}`",
        f"🕒 结束时间: `{bj_time.split(' ')[1]}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for r in all_results:
        status = r.get("status", "未知")
        icon = "✅" if "成功" in status else ("⚠️" if "已签" in status or "未找到" in status else "❌")
        safe_user = r.get("username", "unknown").replace('_', '\\_')
        report_lines.append(
            f"👤 **用户账号** | `{safe_user}`\n"
            f"📳 **签到状态** | {icon} {status}\n"
            f"💵 **余额变动** | `{r.get('pre', '$0.00')}` -> `{r.get('post', '$0.00')}`\n"
            f"🎁 **本次奖励** | `+{r.get('reward', '$0.00')}`\n"
            "────────────────────────"
        )

    success_count = sum(1 for r in all_results if ("成功" in r.get("status", "") or "已签" in r.get("status", "")))
    report_lines.append(f"📙 统计: 已处理 `{len(all_results)}` 个账号，正常 `{success_count}` 个。")

    full_message = "\n".join(report_lines)
    send_tg_notification(final_photo if os.path.exists(final_photo) else None, full_message)

    print("📙 所有任务处理完毕并已发送汇总通知。")
