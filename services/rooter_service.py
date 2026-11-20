"""
Rooter automation service using Playwright.
Handles gaming shop navigation, user authentication, PlayStation wallet voucher search, redemption/checkout, and PIN extraction.
"""

import asyncio
import logging
import re
import time
import datetime
from typing import Optional, List, Callable, Awaitable
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from services.base_platform import BasePlatform, CardItem, PurchaseResult, ProgressCallback
from services.browser_manager import browser_manager

logger = logging.getLogger(__name__)

class RooterService(BasePlatform):
    """Playwright scraper for Rooter Shop PlayStation and Google Play voucher automation."""

    def __init__(self):
        super().__init__(
            platform_id="rooter",
            name="Rooter",
            base_url="https://shop.rooter.gg"
        )
        self.playstation_url = getattr(config, "ROOTER_PLAYSTATION_URL", "https://shop.rooter.gg/product/playstation-gift-cards")
        self.google_play_url = getattr(config, "ROOTER_GOOGLE_PLAY_URL", "https://shop.rooter.gg/product/google-play-gift-card")

    def get_product_info(self, denomination: int) -> dict:
        """Returns product url, name, and type based on denomination."""
        if denomination == 10:
            return {
                "type": "google_play",
                "name": "Google Play Recharge Code",
                "url": self.google_play_url,
                "expected_price": 8.0,
            }
        return {
            "type": "playstation",
            "name": "PlayStation Gift Card",
            "url": self.playstation_url,
            "expected_price": float(denomination) if denomination > 0 else float(getattr(config, "TARGET_DENOMINATION", 5000)),
        }

    async def check_login_status(self, page: Page) -> bool:
        """Verifies if user is logged into Rooter."""
        try:
            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1500)

            # Check if login button is visible
            login_btn = page.locator("button:has-text('Login'), button:has-text('Sign In'), div:has-text('Login / Register')").first
            if await login_btn.is_visible(timeout=3000):
                return False

            # Check for profile icon / coin balance
            profile = page.locator("div[class*='Profile'], img[alt*='avatar'], div[class*='coin-balance']").first
            return await profile.is_visible(timeout=2000)
        except Exception as e:
            logger.warning(f"Error checking Rooter login status: {e}")
            return False

    async def perform_login(
        self,
        page: Page,
        phone_number: str,
        otp_callback: Callable[[], Awaitable[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Logs into Rooter via mobile number and SMS OTP."""
        try:
            if progress_callback:
                await progress_callback("Navigating to Rooter login...", "🔍")

            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")

            # Click login button
            login_btn = page.locator("button:has-text('Login'), div:has-text('Login')").first
            await login_btn.click(timeout=5000)
            await page.wait_for_timeout(1000)

            # Fill phone number
            clean_phone = re.sub(r"\D", "", phone_number)[-10:]
            phone_input = page.locator("input[type='tel'], input[placeholder*='Mobile'], input[name*='phone']").first
            await phone_input.fill(clean_phone)
            await page.wait_for_timeout(500)

            # Submit phone to request OTP
            get_otp_btn = page.locator("button:has-text('Get OTP'), button:has-text('Continue'), button:has-text('Next')").first
            await get_otp_btn.click()

            if progress_callback:
                await progress_callback(f"OTP sent to +91 {clean_phone}. Please reply with OTP in chat...", "📩")

            # Await OTP code from user
            otp_code = await otp_callback()
            if not otp_code:
                logger.error("No OTP provided for Rooter login.")
                return False

            clean_otp = re.sub(r"\D", "", otp_code)

            # Fill OTP inputs
            otp_inputs = page.locator("input[type='number'], input[inputmode='numeric']")
            count = await otp_inputs.count()
            if count > 1:
                for i in range(min(count, len(clean_otp))):
                    await otp_inputs.nth(i).fill(clean_otp[i])
            else:
                single_input = page.locator("input[placeholder*='OTP'], input[name*='otp']").first
                await single_input.fill(clean_otp)

            await page.wait_for_timeout(800)

            # Click verify
            verify_btn = page.locator("button:has-text('Verify'), button:has-text('Submit')").first
            if await verify_btn.is_visible(timeout=2000):
                await verify_btn.click()

            await page.wait_for_load_state("networkidle", timeout=10000)
            if progress_callback:
                await progress_callback("Rooter account verified successfully!", "✅")
            return True

        except Exception as e:
            logger.error(f"Error during Rooter login: {e}")
            return False

    async def search_playstation_cards(
        self,
        page: Page,
        denomination: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[CardItem]:
        """Navigates directly to Rooter gift card pages and checks available options."""
        cards: List[CardItem] = []

        # If user asked specifically for Google Play (e.g. 10)
        if denomination == 10:
            in_stock = await self.check_is_in_stock(page, 10)
            cards.append(CardItem(
                title="Google Play Recharge Code ₹10",
                denomination=10,
                price=8.0,
                platform="rooter",
                in_stock=in_stock,
            ))
            return cards

        target_url = self.playstation_url
        if target_url not in page.url:
            if progress_callback:
                await progress_callback("Opening Rooter PlayStation Gift Cards page...", "🔍")
            await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

        # Include Google Play ₹10 test option if searching all
        if not denomination:
            cards.append(CardItem(
                title="Google Play Recharge Code ₹10 (Test)",
                denomination=10,
                price=8.0,
                platform="rooter",
                in_stock=True,
            ))

        supported = [getattr(config, 'TARGET_DENOMINATION', 5000)]
        for d in supported:
            opt_locator = page.locator("div, span, p").filter(has_text=re.compile(rf"Rs\.?\s*{d}\s*Wallet Code", re.IGNORECASE))
            in_stock = False

            try:
                if await opt_locator.count() > 0:
                    parent_text = await opt_locator.first.locator("xpath=..").inner_text()
                    in_stock = "out of stock" not in parent_text.lower()
                else:
                    simple_opt = page.locator("div").filter(has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE))
                    if await simple_opt.count() > 0:
                        in_stock = "out of stock" not in (await simple_opt.first.inner_text()).lower()
            except Exception:
                in_stock = False

            cards.append(CardItem(
                title=f"Rooter PlayStation Voucher ₹{d:,}",
                denomination=d,
                price=float(d),
                platform="rooter",
                in_stock=in_stock,
            ))

        if denomination:
            cards = [c for c in cards if c.denomination == denomination]

        return cards

    async def dismiss_location_popup(self, page: Page):
        """Auto-dismisses 'Different Location Detected' modal by clicking 'No, stay on this site'."""
        try:
            stay_btn = page.locator("button:has-text('stay on this site'), button:has-text('No, stay on this site'), button:has-text('Stay on this site')").first
            if await stay_btn.is_visible(timeout=800):
                await stay_btn.click(force=True, timeout=1000)
                logger.info("[Rooter] Clicked 'No, stay on this site' on Different Location modal.")
                await page.wait_for_timeout(300)
        except Exception:
            pass

    async def _read_playstation_stock_map(self, page: Page, wait_ms: int = 600) -> dict:
        """Waits for Mantine chip roots to mount and reads live stock availability for all denominations."""
        try:
            await page.wait_for_selector(".mantine-Chip-root", state="visible", timeout=10000)
        except Exception:
            pass
        if wait_ms > 0:
            await page.wait_for_timeout(wait_ms)
        await self.dismiss_location_popup(page)

        return await page.evaluate("""() => {
            const results = {};
            const chips = Array.from(document.querySelectorAll('.mantine-Chip-root'));
            for (const root of chips) {
                const text = (root.innerText || root.textContent || '').toLowerCase();
                const input = root.querySelector('input');
                const isDisabled = (input && input.disabled) || root.getAttribute('data-disabled') === 'true' || !!root.querySelector('[data-disabled="true"]');
                const hasOutOfStock = text.includes('out of stock') || text.includes('sold out');
                for (const denom of [5000, 4000, 3000, 2000, 1000]) {
                    if (new RegExp(denom + '\\\\s*wallet\\\\s*code', 'i').test(text)) {
                        results[String(denom)] = (!isDisabled && !hasOutOfStock);
                    }
                }
            }
            return results;
        }""")

    async def get_in_stock_playstation_denominations(self, page: Page) -> List[int]:
        """Returns all PlayStation denominations currently in stock, sorted from highest to lowest (₹5k -> ₹1k)."""
        in_stock_list = []
        try:
            target_url = self.playstation_url
            if target_url not in page.url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)

            await self.dismiss_location_popup(page)
            stock_map = await self._read_playstation_stock_map(page, wait_ms=600)

            for d in [5000, 4000, 3000, 2000, 1000]:
                if stock_map.get(str(d)):
                    logger.info(f"🚨 [Rooter] In-stock candidate card found: ₹{d}!")
                    in_stock_list.append(d)
        except Exception as e:
            logger.warning(f"Error checking in-stock denominations: {e}")

        return in_stock_list

    async def find_available_playstation_denomination(self, page: Page) -> Optional[int]:
        """Finds the highest PlayStation denomination currently in stock on Rooter (₹5k -> ₹1k)."""
        denoms = await self.get_in_stock_playstation_denominations(page)
        return denoms[0] if denoms else None

    async def check_is_in_stock(self, page: Page, denomination: int) -> bool:
        """Accurate, fast denomination-specific check on Rooter product pages."""
        try:
            if denomination in (4000, 4):
                denomination = getattr(config, "TARGET_DENOMINATION", 5000)
            prod_info = self.get_product_info(denomination)
            target_url = prod_info["url"]

            if target_url not in page.url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)

            await self.dismiss_location_popup(page)

            # A. Google Play Recharge Code (₹10 Test Buy)
            if prod_info["type"] == "google_play":
                try:
                    btn = await page.wait_for_selector(
                        "button[data-testid='proceed-to-pay'], button[data-testid='add-address-btn'], button:has-text('Pay via wallet'), button:has-text('Pay'), button:has-text('Buy Now'), button:has-text('Out of Stock')",
                        timeout=10000
                    )
                    if btn:
                        txt = await btn.inner_text()
                        if "out of stock" in txt.lower():
                            logger.info("[Rooter] Google Play is Out of Stock.")
                            return False
                        logger.info(f"🚨 [Rooter] IN STOCK: Google Play ₹{denomination} is active ({txt.strip()})!")
                        return True
                except Exception as be:
                    logger.warning(f"Could not find Google Play action button: {be}")
                    return False
                return False

            # B. PlayStation Gift Cards (₹1,000 to ₹5,000)
            else:
                stock_map = await self._read_playstation_stock_map(page, wait_ms=600)
                is_in_stock = bool(stock_map.get(str(denomination)))

                if is_in_stock:
                    logger.info(f"🚨 [Rooter] IN STOCK: PlayStation ₹{denomination:,} is active and available!")
                    return True
                else:
                    logger.debug(f"[Rooter] PlayStation ₹{denomination:,} is currently Out of Stock.")
                    return False
        except Exception as e:
            logger.warning(f"Error checking Rooter stock: {e}")
            return False

    async def execute_buy_flow(
        self,
        page: Page,
        denomination: int,
        quantity: int = 1,
        account_label: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        simulation: bool = False,
    ) -> PurchaseResult:
        """Completes ultra-fast automated voucher purchase on Rooter with Rooter Wallet balance."""
        shot_path = None
        if denomination in (4000, 4):
            denomination = getattr(config, "TARGET_DENOMINATION", 5000)
        try:
            prod_info = self.get_product_info(denomination)
            target_url = prod_info["url"]
            prod_name = prod_info["name"]

            navigated = False
            if target_url not in page.url:
                navigated = True
                if progress_callback:
                    await progress_callback(f"Navigating to {prod_name} page...", "🔍")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)

            await self.dismiss_location_popup(page)

            # 1. Select the specific denomination
            if prod_info["type"] == "google_play":
                if navigated:
                    await page.wait_for_timeout(500)
            else:
                # If we reused an already-open monitor page, chips are already hydrated -> only 100ms wait
                stock_map = await self._read_playstation_stock_map(page, wait_ms=500 if navigated else 100)
                if not stock_map.get(str(denomination)):
                    return PurchaseResult(
                        success=False,
                        platform="rooter",
                        denomination=denomination,
                        quantity=quantity,
                        account_label=account_label,
                        message=f"Rooter {prod_name} ₹{denomination:,} is currently Out of Stock!",
                    )

                # Select the exact Mantine chip for this denomination and await billing sync
                chip_root = page.locator(".mantine-Chip-root").filter(
                    has_text=re.compile(rf"Rs\.?\s*{denomination}\s*Wallet Code", re.IGNORECASE)
                ).first

                if await chip_root.count() == 0:
                    return PurchaseResult(
                        success=False,
                        platform="rooter",
                        denomination=denomination,
                        quantity=quantity,
                        account_label=account_label,
                        message=f"Rooter {prod_name} ₹{denomination:,} chip not found in DOM!",
                        error_screenshot=shot_path,
                    )

                # Await Rooter's backend order/billing API response so cart updates to requested denomination
                try:
                    await chip_root.scroll_into_view_if_needed(timeout=2000)
                    async with page.expect_response(
                        lambda r: "order/billing" in r.url and r.status in (200, 201),
                        timeout=4000
                    ):
                        # 1) Physical pixel coordinate click on chip center
                        box = await chip_root.bounding_box()
                        if box:
                            cx = box['x'] + box['width'] / 2
                            cy = box['y'] + box['height'] / 2
                            await page.mouse.click(cx, cy)
                            logger.info(f"[Rooter] Pixel click executed on ₹{denomination:,} chip at ({cx:.1f}, {cy:.1f})")

                        # 2) Trigger React Fiber onSelectVariation(obj) on Rooter component
                        await page.evaluate("""(targetDenom) => {
                            const chips = Array.from(document.querySelectorAll('.mantine-Chip-root'));
                            for (const chip of chips) {
                                const k = Object.keys(chip).find(x => x.startsWith('__reactFiber$'));
                                let curr = chip[k];
                                while (curr) {
                                    if (curr.memoizedProps && curr.memoizedProps.onSelectVariation) {
                                        const p = curr.memoizedProps;
                                        const text = (p.obj && p.obj.name ? p.obj.name : chip.innerText || '').toLowerCase();
                                        if (new RegExp(targetDenom + '\\\\s*wallet\\\\s*code', 'i').test(text)) {
                                            p.onSelectVariation(p.obj);
                                            return true;
                                        }
                                    }
                                    curr = curr.return;
                                }
                            }
                            return false;
                        }""", denomination)
                    logger.info(f"[Rooter] order/billing API confirmed 200/201 response for ₹{denomination:,}!")
                except Exception as be:
                    logger.warning(f"[Rooter] Billing API wait notice: {be}. Continuing with DOM verification...")

                # Small settle delay for React state and DOM indicators to reflect
                await page.wait_for_timeout(350)

                # Pre-Checkout Strict Verification: verify active chip is strictly the target denomination
                selected_info = None
                try:
                    selected_info = await page.evaluate("""() => {
                        const chips = Array.from(document.querySelectorAll('.mantine-Chip-root'));
                        for (const root of chips) {
                            const k = Object.keys(root).find(x => x.startsWith('__reactFiber$'));
                            let curr = root[k];
                            let p = null;
                            while (curr) {
                                if (curr.memoizedProps && curr.memoizedProps.onSelectVariation) {
                                    p = curr.memoizedProps;
                                    break;
                                }
                                curr = curr.return;
                            }
                            const inp = root.querySelector('input');
                            const lbl = root.querySelector('label');
                            const isSelected = (p && p.obj && p.selectedChip === p.obj.id) ||
                                              (inp && inp.checked) ||
                                              (lbl && lbl.getAttribute('data-checked') === 'true') ||
                                              (root.getAttribute('data-selected') === 'true');
                            if (isSelected) {
                                const m = (root.innerText || (p && p.obj ? p.obj.name : '')).match(/Rs\.?\s*([0-9]+)\s*Wallet Code/i);
                                if (m) return parseInt(m[1]);
                            }
                        }
                        return null;
                    }""")
                except Exception as ve:
                    logger.debug(f"Selected chip evaluation notice: {ve}")

                logger.info(f"[Rooter] Selected chip denomination on page verified: ₹{selected_info}")
                if selected_info != denomination:
                    shot_path = await browser_manager.capture_screenshot(page, f"selection_fail_{denomination}")
                    logger.error(f"[Rooter] STRICT GUARD: Active selection is {selected_info} instead of ₹{denomination:,}! Aborting.")
                    return PurchaseResult(
                        success=False,
                        platform="rooter",
                        denomination=denomination,
                        quantity=quantity,
                        account_label=account_label,
                        message=f"Strict Guard: Selection verification failed (page shows {selected_info} instead of ₹{denomination:,}). Aborted purchase.",
                        error_screenshot=shot_path,
                    )

                # Verify bottom button payable amount (poll briefly for React sync)
                verify_btn = page.locator(
                    "button[data-testid='proceed-to-pay'], "
                    "button[data-testid='add-address-btn'], "
                    "button:has-text('Pay via wallet'), "
                    "button:has-text('Pay ₹'), "
                    "button:has-text('Buy Now'), "
                    "button:has-text('Proceed')"
                ).first
                if await verify_btn.is_visible(timeout=2000):
                    btn_val = None
                    for _ in range(5):
                        btn_text = await verify_btn.inner_text()
                        if "out of stock" in btn_text.lower():
                            return PurchaseResult(
                                success=False,
                                platform="rooter",
                                denomination=denomination,
                                quantity=quantity,
                                account_label=account_label,
                                message=f"Selected ₹{denomination:,} showed '{btn_text.strip()}' before checkout.",
                                error_screenshot=shot_path,
                            )
                        match_price = re.search(r"(?:Pay\s*₹?|₹\s*)([0-9,]+(?:\.[0-9]+)?)", btn_text, re.IGNORECASE)
                        if match_price:
                            btn_val = float(match_price.group(1).replace(",", ""))
                            if denomination == 5000 and btn_val < 4500:
                                await page.wait_for_timeout(150)
                                continue
                            elif denomination == 4000 and btn_val < 3500:
                                await page.wait_for_timeout(150)
                                continue
                        break
                    if btn_val is not None:
                        logger.info(f"[Rooter] Bottom button payable amount detected: ₹{btn_val}")
                        if denomination == 5000 and btn_val < 4500:
                            logger.error(f"[Rooter] STRICT 5K GUARD: Bottom button payable shows ₹{btn_val} (< ₹4,500). Aborting to prevent wrong buy!")
                            return PurchaseResult(
                                success=False,
                                platform="rooter",
                                denomination=denomination,
                                quantity=quantity,
                                account_label=account_label,
                                message=f"Strict 5K Guard: Payable amount is ₹{btn_val:,.0f} (< ₹4,500). Aborted to prevent wrong buy.",
                            )
                        elif denomination == 4000 and btn_val < 3500:
                            logger.error(f"[Rooter] STRICT 4K GUARD: Bottom button payable shows ₹{btn_val} (< ₹3,500). Aborting to prevent 1K purchase!")
                            return PurchaseResult(
                                success=False,
                                platform="rooter",
                                denomination=denomination,
                                quantity=quantity,
                                account_label=account_label,
                                message=f"Strict 4K Guard: Payable amount is ₹{btn_val:,.0f} (₹1,000 card was selected). Aborted to prevent wrong buy.",
                            )

                # Increment quantity if quantity > 1 (e.g. 2 per order)
                if quantity > 1:
                    try:
                        plus_btn = page.locator("button:has-text('+'), div[class*='qty'] button:has-text('+'), div[class*='quantity'] button:has-text('+'), [aria-label*='increase']").first
                        if await plus_btn.is_visible(timeout=1000) and not await plus_btn.is_disabled():
                            for _ in range(quantity - 1):
                                await plus_btn.click(force=True, timeout=1000)
                                await page.wait_for_timeout(300)
                        else:
                            logger.info("[Rooter] Quantity '+' button is disabled or not found; proceeding with quantity 1.")
                            quantity = 1
                    except Exception as qe:
                        logger.debug(f"Could not increment quantity, proceeding with 1: {qe}")
                        quantity = 1

            # 2. Check if main action button is disabled / Out of Stock
            await self.dismiss_location_popup(page)
            out_btn = page.locator("button:has-text('Out of Stock')").first
            if await out_btn.is_visible(timeout=1000):
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message=f"{prod_name} ₹{denomination:,} went out of stock right before checkout!",
                )

            # 3. Handle Simulation Mode
            if simulation:
                if progress_callback:
                    await progress_callback(f"SIMULATION MODE: {prod_name} stock verified! Simulating dry-run purchase...", "💳")
                await page.wait_for_timeout(1500)

                prefix = "GOOG" if prod_info["type"] == "google_play" else "PSN"
                mock_code = f"ROTR-{prefix}-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"RTR-ORD-{int(asyncio.get_event_loop().time())}"

                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    codes=[mock_code] if quantity == 1 else [mock_code, f"{mock_code}-2"],
                    order_id=mock_order,
                    receipt_summary=f"Rooter {prod_name} ₹{denomination:,} x{quantity} [SIMULATION]",
                    message="Purchase flow simulated successfully in dry-run mode. Turn off SIMULATION_MODE to purchase with real balance.",
                    simulation=True,
                )

            # 4. Live Purchase Execution
            if progress_callback:
                await progress_callback(f"Clicking Buy / Pay on {prod_name}...", "🛒")

            # 1. Scoped visible modal locator: detects open Delivery Details / Checkout / Payment modal
            modal_locator = page.locator(
                "section.mantine-Modal-content:visible, "
                "div.mantine-Modal-content:visible, "
                "section[role='dialog']:visible, "
                "div[role='dialog']:visible, "
                ".mantine-Modal-content:visible"
            ).filter(has_text=re.compile(r"Delivery\s*Details|Checkout|Pay\s*via|Order\s*Summary|Payment", re.I)).first

            modal_open = False
            try:
                modal_open = await modal_locator.is_visible(timeout=300)
            except Exception:
                pass

            # 2. If modal is NOT already open, click the main page action button
            if not modal_open:
                buy_btn = page.locator(
                    "button[data-testid='add-address-btn'], "
                    "button[data-testid='proceed-to-pay'], "
                    "button:has-text('Pay via wallet'), "
                    "button:has-text('Pay via Rooter'), "
                    "button:has-text('Pay ₹'), "
                    "button:has-text('Buy Now'), "
                    "button:has-text('Proceed')"
                ).first
                if await buy_btn.is_visible(timeout=3000):
                    buy_btn_txt = (await buy_btn.inner_text() or "").strip()
                    if "out of stock" in buy_btn_txt.lower():
                        return PurchaseResult(
                            success=False,
                            platform="rooter",
                            denomination=denomination,
                            quantity=quantity,
                            account_label=account_label,
                            message=f"Selected ₹{denomination:,} showed '{buy_btn_txt}' before checkout click.",
                            error_screenshot=shot_path,
                        )
                    try:
                        await buy_btn.click(force=True, timeout=3000)
                    except Exception:
                        try:
                            await buy_btn.dispatch_event("click")
                        except Exception:
                            pass

            # 3. Inspect Delivery Details / Checkout modal strictly inside visible modal container
            modal_text = ""
            modal_open = False
            target_modal = None
            for _ in range(16):  # Poll up to 4.0 seconds for modal to mount and render children
                try:
                    if await modal_locator.is_visible(timeout=250):
                        target_modal = modal_locator
                        modal_open = True
                        m_raw = (await target_modal.inner_text() or "").strip()
                        if len(m_raw) > 5:
                            modal_text = m_raw
                            break
                    else:
                        # Fallback: check any visible mantine-Modal-content
                        fallback_modal = page.locator(
                            "section.mantine-Modal-content:visible, "
                            "div.mantine-Modal-content:visible, "
                            ".mantine-Modal-content:visible"
                        ).first
                        if await fallback_modal.is_visible(timeout=100):
                            m_raw = (await fallback_modal.inner_text() or "").strip()
                            if len(m_raw) > 5:
                                target_modal = fallback_modal
                                modal_open = True
                                modal_text = m_raw
                                break
                except Exception:
                    pass
                await page.wait_for_timeout(250)

            # If modal still not open, retry clicking buy_btn once more
            if not modal_open:
                try:
                    retry_buy = page.locator("button[data-testid='add-address-btn'], button:has-text('Pay via wallet')").first
                    if await retry_buy.is_visible(timeout=500):
                        await retry_buy.dispatch_event("click")
                        await page.wait_for_timeout(500)
                        if await modal_locator.is_visible(timeout=1000):
                            target_modal = modal_locator
                            modal_open = True
                            modal_text = (await target_modal.inner_text() or "").strip()
                except Exception:
                    pass

            if not modal_open or not target_modal:
                shot_path = await browser_manager.capture_screenshot(page, f"modal_open_fail_{denomination}")
                logger.error("[Rooter] STRICT GUARD: Checkout modal did not open or render content! Aborting.")
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message="Strict Guard: Checkout modal did not render content. Aborted to prevent wrong buy.",
                    error_screenshot=shot_path,
                )

            # Auto-fill Name / Email in Delivery Details modal if empty so payment button activates
            try:
                name_inp = target_modal.locator("input[placeholder*='name' i], input[name*='name' i]").first
                if await name_inp.is_visible(timeout=300):
                    curr_name = (await name_inp.input_value() or "").strip()
                    if not curr_name:
                        await name_inp.fill("Aakash")

                email_inp = target_modal.locator("input[placeholder*='email' i], input[name*='email' i]").first
                if await email_inp.is_visible(timeout=300):
                    curr_email = (await email_inp.input_value() or "").strip()
                    if not curr_email:
                        await email_inp.fill("aakashlohar7@gmail.com")
            except Exception as e_fill:
                logger.debug(f"[Rooter] Delivery details field auto-fill note: {e_fill}")

            # Extract exact denomination if explicitly present in modal content
            modal_val = None
            m_denom_match = re.search(r"Rs\.?\s*([0-9]+)\s*Wallet Code", modal_text, re.IGNORECASE)
            if m_denom_match:
                modal_val = int(m_denom_match.group(1))
            else:
                m_alt = re.search(r"(?:₹|Rs\.?)\s*([0-9,]+)", modal_text)
                if m_alt:
                    parsed_alt = int(m_alt.group(1).replace(",", "").split(".")[0])
                    if parsed_alt in (1000, 2000, 3000, 4000, 5000):
                        modal_val = parsed_alt

            # STRICT GUARD: If modal explicitly specifies a denomination that does not match target, ABORT!
            if modal_val is not None:
                logger.info(f"[Rooter] Checkout modal item confirmed as: {modal_val}")
                if modal_val != denomination:
                    shot_path = await browser_manager.capture_screenshot(page, f"modal_mismatch_{denomination}")
                    logger.error(f"[Rooter] CRITICAL GUARD: Wanted ₹{denomination:,} but modal shows {modal_val}! ABORTING.")
                    return PurchaseResult(
                        success=False,
                        platform="rooter",
                        denomination=denomination,
                        quantity=quantity,
                        account_label=account_label,
                        message=f"Strict Guard: Rooter checkout modal selected {modal_val} instead of ₹{denomination:,}! Aborted purchase to prevent wrong buy.",
                        error_screenshot=shot_path,
                    )
            else:
                logger.info(f"[Rooter] Delivery Details modal active for ₹{denomination:,}. Proceeding with wallet purchase!")

            async def _poll_post_click(max_ms: int = 4500) -> str:
                steps = max(1, max_ms // 250)
                for _ in range(steps):
                    await page.wait_for_timeout(250)
                    try:
                        txt = (await page.locator("body").inner_text() or "").lower()
                    except Exception:
                        txt = ""
                    if any(k in txt for k in ("order placed", "payment successful", "purchase successful", "order confirmed", "thank you for your order")):
                        return "success"
                    if re.search(r"redeem\s*code|voucher\s*code|gift\s*code", txt):
                        return "success"
                    if any(k in txt for k in ("insufficient", "not enough balance", "add money", "low balance", "out of stock", "recharge", "payment failed", "failed to pay")):
                        return "abort"
                    if "enter mobile" in txt or "verify otp" in txt:
                        return "login"
                    try:
                        if target_modal and not await target_modal.is_visible(timeout=100):
                            return "closed"
                    except Exception:
                        pass
                return "timeout"

            # Click primary Pay button scoped strictly inside the open modal
            modal_pay_btn = target_modal.locator(
                "button[data-testid='add-address-btn'], "
                "button[data-testid='proceed-to-pay'], "
                "button:has-text('Pay via wallet'), "
                "button:has-text('Pay via Rooter'), "
                "button:has-text('Pay ₹'), "
                "button:has-text('Proceed to Pay'), "
                "button:has-text('Pay Now'), "
                "button:has-text('Continue'), "
                "button:has-text('Proceed')"
            ).first
            click_outcome = "none"
            if await modal_pay_btn.is_visible(timeout=2000):
                if progress_callback:
                    await progress_callback("Confirming Delivery Details & submitting order...", "📝")
                logger.info("[Rooter] Clicking Pay button inside checkout modal...")
                try:
                    await modal_pay_btn.click(force=True, timeout=3000)
                except Exception:
                    try:
                        await modal_pay_btn.dispatch_event("click")
                    except Exception:
                        pass
                click_outcome = await _poll_post_click(3000)

            if click_outcome == "none" or click_outcome == "timeout":
                # Close coupon or offer popup if shown inside modal
                close_coupon = page.locator(
                    "button:has-text('Skip'), "
                    "button[aria-label*='Close'], "
                    "button[data-testid='close-modal-btn']"
                ).first
                if await close_coupon.is_visible(timeout=500):
                    try:
                        await close_coupon.click(force=True, timeout=1000)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

                # Select Rooter Wallet / Balance payment method strictly inside modal/payment dialog
                wallet_opt = page.locator(
                    "button, label, input[type='radio'], div[role='radio'], div[role='button']"
                ).filter(has_text=re.compile(r"(?:Rooter\s*Wallet|Wallet\s*Balance|Pay\s*via\s*Wallet|Rooter\s*Pay|Rooter\s*Credits)", re.IGNORECASE)).first
                if await wallet_opt.is_visible(timeout=800):
                    try:
                        await wallet_opt.click(force=True, timeout=1500)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

                # Confirm payment / final proceed button if modal is still open
                confirm_pay = page.locator(
                    "button[data-testid='proceed-to-pay'], "
                    "button[data-testid='add-address-btn'], "
                    "button:has-text('Pay via wallet'), "
                    "button:has-text('Pay via Rooter'), "
                    "button:has-text('Pay ₹'), "
                    "button:has-text('Pay Now'), "
                    "button:has-text('Proceed to Pay')"
                ).last
                if await confirm_pay.is_visible(timeout=1200):
                    try:
                        await confirm_pay.click(force=True, timeout=2500)
                        await _poll_post_click(4500)
                    except Exception:
                        pass

            # Capture confirmation screenshot
            shot_path = await browser_manager.capture_screenshot(page, f"order_{prod_info['type']}_{denomination}")

            # Inspect page content for voucher code or errors
            body_content = await page.locator("body").inner_text()

            # Check for error indicators
            if any(k in body_content.lower() for k in ("insufficient", "low balance", "add money", "recharge", "payment failed", "failed to pay")):
                cost_est = 6030 if denomination == 5000 else int(denomination * 1.206)
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message=f"Rooter wallet balance insufficient for ₹{denomination:,} (Total cost is ₹{cost_est:,} without discount). Please add balance to Rooter wallet.",
                    error_screenshot=shot_path,
                )

            # Check if login modal unexpectedly appeared (e.g. auth expired or not logged in)
            is_login_modal = any(
                p in body_content.lower()
                for p in [
                    "login / sign up",
                    "login / register",
                    "enter your mobile number",
                    "enter mobile number",
                    "continue with google",
                    "have a referral code",
                ]
            )
            if is_login_modal:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Rooter session expired or not logged in! Rooter login popup appeared. Please send /login to bot and paste your Bearer token, or set ROOTER_AUTH_TOKEN in Railway variables.",
                    error_screenshot=shot_path,
                )

            # Search for Code, PIN, Order ID on current page
            code_match = re.search(r"(?:Code\s*#?\d*|Voucher|Key|Redeem\s*Code|Coupon\s*Codes?)[\s:\n]+([A-Z0-9-]{10,25})", body_content, re.IGNORECASE)
            if not code_match and prod_info["type"] == "google_play":
                gp_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", body_content, re.IGNORECASE)
                if not gp_match:
                    gp_match = re.search(r"\b([A-Z0-9]{16})\b", body_content)
                if gp_match:
                    code_match = gp_match

            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", body_content, re.IGNORECASE)
            order_match = re.search(r"(?:Order\s*Id|Txn\s*ID|Reference)[\s:]*#?([A-Z0-9_-]+)", body_content, re.IGNORECASE)

            # Success indicators — STRICT: only Rooter-specific post-purchase phrases
            # Removed generic words like "thank you" / "congratulations" that appear on many pages
            success_indicators = [
                "delivered successfully", "items delivered", "item purchased", "coupon codes",
                "paid amount", "order placed", "order successful", "purchase successful",
                "transaction successful", "redeem code",
            ]
            is_successful_order = any(ind in body_content.lower() for ind in success_indicators) or (code_match is not None)

            # If code was not found directly on post-checkout page, auto-fetch from Rooter profile/orders
            # IMPORTANT: We record the time BEFORE navigating to orders page so we can verify
            # the fetched order is actually from THIS purchase (not a previous one).
            purchase_unix_time = int(time.time())
            if not code_match:
                try:
                    logger.info("[Rooter] Checking profile/orders to extract latest voucher code...")
                    await page.goto("https://shop.rooter.gg/profile/orders", wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2500)

                    # Click top order card to view coupon code
                    order_card = page.locator("text='PlayStation Gift Card', text='PlayStation Gift Cards', text='Rs.5000 Wallet Code', text='Rs.4000 Wallet Code', text='Google Play Recharge Code', div[class*='order']").first
                    if await order_card.is_visible(timeout=3000):
                        await order_card.click()
                        await page.wait_for_timeout(2000)

                    orders_body = await page.locator("body").inner_text()

                    # CRITICAL FIX: Verify this is a FRESH order (placed within recent minutes).
                    # Rooter displays timestamps like "11:29 AM, 14 Nov, 2026" and "items delivered successfully"
                    now_dt = datetime.datetime.now()
                    today_str_1 = now_dt.strftime("%d %b").lower()  # e.g. "14 nov"
                    today_str_2 = now_dt.strftime("%d %B").lower()  # e.g. "14 november"
                    today_str_3 = f"{now_dt.day} {now_dt.strftime('%b')}".lower() # e.g. "14 nov" (no leading zero)
                    order_section_snippet = orders_body[:2500].lower()

                    fresh_signals = [
                        "just now", "second", "sec ago", "secs ago",
                        "1 minute", "2 minute", "3 minute", "4 minute", "5 minute",
                        "1 min", "2 min", "3 min", "4 min", "5 min",
                        "minute ago", "minutes ago",
                        "delivered successfully", "items delivered", "item delivered",
                    ]
                    is_fresh_order = any(sig in order_section_snippet for sig in fresh_signals)

                    # Also verify today's date appears near the top order card
                    if any(td in order_section_snippet for td in (today_str_1, today_str_2, today_str_3)):
                        is_fresh_order = True

                    # Check Rooter timestamp format: "11:29 AM, 14 Nov, 2026"
                    time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM),?\s*\d{1,2}\s+[A-Za-z]+,?\s*\d{4})", orders_body[:2500], re.IGNORECASE)
                    if time_match:
                        try:
                            t_clean = time_match.group(1).replace(",", "")
                            parsed_dt = datetime.datetime.strptime(t_clean, "%I:%M %p %d %b %Y")
                            if abs((now_dt - parsed_dt).total_seconds()) <= 1200:  # placed within last 20 minutes
                                is_fresh_order = True
                        except Exception:
                            pass

                    orders_order_match = re.search(r"(?:Order\s*Id|Txn\s*ID|Reference)[\s:]*#?([A-Z0-9_-]+)", orders_body, re.IGNORECASE)
                    if is_fresh_order:
                        logger.info("[Rooter] Fresh order confirmed on orders page! Extracting voucher code...")
                        code_match = re.search(r"(?:Code\s*#?\d*|Voucher|Key|Redeem\s*Code|Coupon\s*Codes?)[\s:\n]+([A-Z0-9-]{10,25})", orders_body, re.IGNORECASE)
                        if not code_match and prod_info["type"] == "google_play":
                            code_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", orders_body, re.IGNORECASE)
                            if not code_match:
                                code_match = re.search(r"\b([A-Z0-9]{16})\b", orders_body)

                        if not pin_match:
                            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", orders_body, re.IGNORECASE)
                        if not order_match:
                            order_match = orders_order_match

                        if code_match or any(ind in orders_body.lower() for ind in success_indicators):
                            is_successful_order = True
                            shot_path = await browser_manager.capture_screenshot(page, f"order_{prod_info['type']}_{denomination}")
                    else:
                        # Orders page did not confirm a NEW order — mark as failure to avoid false positives
                        logger.warning("[Rooter] No fresh order detected on orders page. Marking purchase as FAILED to prevent false positive.")
                        is_successful_order = False
                        code_match = None
                except Exception as oe:
                    logger.warning(f"[Rooter] Could not auto-fetch from profile/orders: {oe}")

            if not is_successful_order and not code_match:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message="Order submitted, but order confirmation was not detected on page. Please verify your Rooter profile / Orders tab.",
                    error_screenshot=shot_path,
                )

            code = code_match.group(1) if code_match else "Check Orders Tab in Rooter"
            pin = pin_match.group(1) if pin_match else "N/A"
            order_id = order_match.group(1) if order_match else f"RTR-{int(asyncio.get_event_loop().time())}"

            # Extract all voucher codes found if quantity > 1
            active_body = orders_body if 'orders_body' in locals() else body_content
            all_found_codes = re.findall(r"(?:Code\s*#?\d*|Voucher|Key|Redeem\s*Code|Coupon\s*Codes?)[\s:\n]+([A-Z0-9-]{10,25})", active_body, re.IGNORECASE)
            codes_list = list(dict.fromkeys(all_found_codes)) if all_found_codes else ([code] if code else [])

            # Extract actual bought denomination from confirmation text
            real_bought_denom = denomination
            actual_denom_match = re.search(r"Rs\.?\s*([0-9]+)\s*Wallet Code", active_body, re.IGNORECASE)
            if actual_denom_match:
                try:
                    parsed_denom = int(actual_denom_match.group(1))
                    if parsed_denom in (1000, 2000, 3000, 4000, 5000):
                        real_bought_denom = parsed_denom
                except Exception:
                    pass

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=real_bought_denom,
                quantity=quantity,
                account_label=account_label,
                voucher_code=code,
                voucher_pin=pin,
                codes=codes_list,
                order_id=order_id,
                receipt_summary=f"Rooter {prod_name} ₹{real_bought_denom:,} x{quantity}",
                message=f"{prod_name} (x{quantity}) successfully purchased on Rooter with wallet balance!",
                error_screenshot=shot_path,
                simulation=False,
            )

        except Exception as e:
            logger.error(f"Rooter buy flow encountered error: {e}", exc_info=True)
            shot_path = await browser_manager.capture_screenshot(page, "rooter_buy_error")
            return PurchaseResult(
                success=False,
                platform="rooter",
                denomination=denomination,
                message=f"Rooter automation error: {str(e)}",
                error_screenshot=shot_path,
            )
