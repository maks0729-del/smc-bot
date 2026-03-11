import aiohttp
import json
from typing import Optional


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


def format_smc_for_prompt(instrument: str, smc: dict, session: dict) -> str:
    """Format SMC data into a structured prompt for Claude."""
    price = smc.get("current_price", 0)
    key = smc.get("key_levels", {})

    def trend_arrow(t):
        return {"bullish": "↑ Bullish", "bearish": "↓ Bearish", "ranging": "↔ Ranging"}.get(t, "? Unknown")

    def ob_str(obs, instrument):
        if not obs:
            return "не знайдено"
        lines = []
        for o in obs[-2:]:
            lines.append(f"  {'Bullish' if 'bullish' in o['type'] else 'Bearish'} OB: {o['bottom']:.5f} — {o['top']:.5f}")
        return "\n".join(lines)

    def fvg_str(fvgs):
        if not fvgs:
            return "не знайдено"
        lines = []
        for f in fvgs[-2:]:
            lines.append(f"  {'Bullish' if 'bullish' in f['type'] else 'Bearish'} FVG: {f['bottom']:.5f} — {f['top']:.5f}")
        return "\n".join(lines)

    def liq_str(liq):
        bsl = liq.get("buy_side", [])
        ssl = liq.get("sell_side", [])
        parts = []
        if bsl:
            bsl_prices = ", ".join("{:.5f}".format(l["price"]) for l in bsl[-2:])
            parts.append(f"  BSL (стопи під): {bsl_prices}")
        if ssl:
            ssl_prices = ", ".join("{:.5f}".format(l["price"]) for l in ssl[-2:])
            parts.append(f"  SSL (стопи над): {ssl_prices}")
        return "\n".join(parts) if parts else "не визначено"

    def sweep_str(sweep):
        if not sweep:
            return "немає"
        return f"  ✅ {sweep['desc']} → очікуваний напрям: {sweep['direction']}"

    def pd_str(pd):
        zone = pd.get("zone", "unknown")
        pct = pd.get("percent", 0)
        eq = pd.get("equilibrium", 0)
        icons = {"premium": "🔴 Premium", "discount": "🟢 Discount", "equilibrium": "🟡 Equilibrium"}
        return f"{icons.get(zone, zone)} ({pct:.1f}% від рейнджу, EQ: {eq:.5f})"

    m_s = smc.get("structure_M", {})
    w_s = smc.get("structure_W", {})
    d_s = smc.get("structure_D", {})
    h4_s = smc.get("structure_H4", {})
    h1_s = smc.get("structure_H1", {})
    m15_s = smc.get("structure_M15", {})

    prompt = f"""Ти досвідчений SMC трейдер. Проведи повний топ-даун аналіз та дай торговий план.

ІНСТРУМЕНТ: {instrument.replace('_', '/')}
ПОТОЧНА ЦІНА: {price:.5f}
СЕСІЯ: {session['name']} {session['emoji']}
ЧАС: UTC

═══ СТРУКТУРА РИНКУ ════════════════════════════
Monthly  : {trend_arrow(m_s.get('trend', 'unknown'))}
Weekly   : {trend_arrow(w_s.get('trend', 'unknown'))}
Daily    : {trend_arrow(d_s.get('trend', 'unknown'))}
4H       : {trend_arrow(h4_s.get('trend', 'unknown'))}
1H       : {trend_arrow(h1_s.get('trend', 'unknown'))}
15M      : {trend_arrow(m15_s.get('trend', 'unknown'))}

═══ КЛЮЧОВІ РІВНІ ══════════════════════════════
PMH: {key.get('PMH', 'N/A')}  |  PML: {key.get('PML', 'N/A')}
PWH: {key.get('PWH', 'N/A')}  |  PWL: {key.get('PWL', 'N/A')}
PDH: {key.get('PDH', 'N/A')}  |  PDL: {key.get('PDL', 'N/A')}

═══ ORDER BLOCKS ════════════════════════════════
4H OB:
{ob_str(smc.get('ob_H4', []), instrument)}
1H OB:
{ob_str(smc.get('ob_H1', []), instrument)}
15M OB:
{ob_str(smc.get('ob_M15', []), instrument)}

═══ FAIR VALUE GAPS (ІМБАЛАНСИ) ════════════════
4H FVG: {fvg_str(smc.get('fvg_H4', []))}
1H FVG: {fvg_str(smc.get('fvg_H1', []))}
15M FVG: {fvg_str(smc.get('fvg_M15', []))}

═══ ЛІКВІДНІСТЬ ════════════════════════════════
1H:
{liq_str(smc.get('liquidity_H1', {}))}
15M:
{liq_str(smc.get('liquidity_M15', {}))}

═══ СВІПИ ЛІКВІДНОСТІ ══════════════════════════
4H: {sweep_str(smc.get('sweep_H4'))}
1H: {sweep_str(smc.get('sweep_H1'))}
15M: {sweep_str(smc.get('sweep_M15'))}

═══ PREMIUM / DISCOUNT ═════════════════════════
4H: {pd_str(smc.get('pd_zone_H4', {}))}
1H: {pd_str(smc.get('pd_zone_H1', {}))}

═══ ЯКІСТЬ СЕТАПУ ══════════════════════════════
Score: {smc.get('setup_quality', 0)}/5
Has Setup: {'✅ ТАК' if smc.get('has_setup') else '❌ НІ'}

═══════════════════════════════════════════════════

ПРАВИЛА ТРЕЙДИНГУ:
- Топ-даун: Monthly → Weekly → Daily → 4H → 1H → 15M
- RR мінімум 1:2, ціль 1:3+
- Ризик на угоду: 0.5-1% від депозиту
- Ціль: prop challenge +8%

На основі цих даних дай відповідь У ФОРМАТІ TELEGRAM (з емодзі та Markdown):

1. BIAS (загальний напрям на основі старших TF)
2. ПОТОЧНА СИТУАЦІЯ (що відбувається зараз)
3. СЦЕНАРІЙ BUY (якщо актуальний): зона входу, SL, TP1, TP2, RR
4. СЦЕНАРІЙ SELL (якщо актуальний): зона входу, SL, TP1, TP2, RR
5. ЩО ЧЕКАТИ (конкретний тригер для входу на 15M)
6. ВИСНОВОК (входити зараз чи чекати)

Відповідай ТІЛЬКИ УКРАЇНСЬКОЮ. Будь конкретним — давай точні рівні цін."""

    return prompt


async def get_ai_analysis(
    instrument: str,
    smc_data: dict,
    session_info: dict,
    api_key: str,
    alert_mode: bool = False
) -> str:
    """Get Claude AI analysis of SMC data."""

    prompt = format_smc_for_prompt(instrument, smc_data, session_info)

    if alert_mode:
        prompt += "\n\nВАЖЛИВО: Це АВТОМАТИЧНИЙ АЛЕРТ. Починай повідомлення з '🚨 ALERT:' і будь дуже коротким — тільки найважливіше: що сталось, куди рухатись, де вхід/SL/TP."

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANTHROPIC_API,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=45)
        ) as resp:
            if resp.status != 200:
                err = await resp.text()
                raise Exception(f"Anthropic API error {resp.status}: {err[:200]}")

            data = await resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []))

    # Add header
    emoji = {"EUR_USD": "🇪🇺", "GBP_USD": "🇬🇧", "XAU_USD": "🥇", "BTC_USD": "₿"}.get(instrument, "📊")
    display = instrument.replace("_", "/")
    price = smc_data.get("current_price", 0)

    header = (
        f"{emoji} *{display}* | `{price:.5f}`\n"
        f"📍 {session_info['name']} {session_info['emoji']} | "
        f"Score: {'⭐' * smc_data.get('setup_quality', 0)}\n"
        f"{'─' * 30}\n\n"
    )

    return header + text
