"""
Stillhalter AI App — Sentiment Analyse v2
Chris Camillo Social Arbitrage: Virale Trends automatisch entdecken →
Produkte identifizieren → Aktien mappen → Einpreisung bewerten.

Quellen: Reddit (hot/rising/new) · Google Trends · StockTwits · Product Hunt · Hacker News
Fokus: Frauen · Teens · Kinder — von Wall Street systematisch übersehene Zielgruppen
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Sentiment Analyse · Stillhalter AI App",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ══════════════════════════════════════════════════════════════════════════════
# BRAND → TICKER DATENBANK
# Demografisches Tagging: W=Frauen, T=Teens, K=Kinder, M=Männer, A=Alle
# ══════════════════════════════════════════════════════════════════════════════
BRAND_TICKER: dict[str, str | None] = {
    # ── Consumer Tech ─────────────────────────────────────────────────────────
    "apple":        "AAPL",  "iphone":       "AAPL",  "airpods":    "AAPL",
    "apple watch":  "AAPL",  "macbook":      "AAPL",  "ipad":       "AAPL",
    "vision pro":   "AAPL",  "apple vision": "AAPL",
    "nvidia":       "NVDA",  "geforce":      "NVDA",  "rtx":        "NVDA",
    "blackwell":    "NVDA",  "h100":         "NVDA",  "b200":       "NVDA",
    "amd":          "AMD",   "ryzen":        "AMD",   "radeon":     "AMD",
    "intel":        "INTC",
    "meta":         "META",  "instagram":    "META",  "quest":      "META",
    "threads":      "META",  "ray-ban meta": "META",  "reels":      "META",
    "google":       "GOOGL", "pixel":        "GOOGL", "gemini":     "GOOGL",
    "waymo":        "GOOGL", "google maps":  "GOOGL",
    "microsoft":    "MSFT",  "xbox":         "MSFT",  "copilot":    "MSFT",
    "azure":        "MSFT",  "github":       "MSFT",  "surface":    "MSFT",
    "minecraft":    "MSFT",
    "sony":         "SONY",  "playstation":  "SONY",  "ps5":        "SONY",
    "nintendo":     "NTDOY", "switch":       "NTDOY", "pokemon":    "NTDOY",
    "amazon":       "AMZN",  "prime video":  "AMZN",  "kindle":     "AMZN",
    "aws":          "AMZN",  "alexa":        "AMZN",  "ring":       "AMZN",
    "netflix":      "NFLX",
    "spotify":      "SPOT",
    "arm":          "ARM",
    "palantir":     "PLTR",
    "openai":       None,    "chatgpt":      "MSFT",  "gpt-4":      "MSFT",
    "claude":       None,    "anthropic":    None,
    "snowflake":    "SNOW",
    "salesforce":   "CRM",
    "servicenow":   "NOW",
    "datadog":      "DDOG",
    "crowdstrike":  "CRWD",
    "palo alto":    "PANW",

    # ── 👩 BEAUTY / SKINCARE (Wall Street übersieht das!) ─────────────────────
    "e.l.f":        "ELF",   "elf beauty":   "ELF",   "elf cosmetics": "ELF",
    "ulta":         "ULTA",  "ulta beauty":  "ULTA",
    "olaplex":      "OLPX",
    "estee lauder": "EL",    "clinique":     "EL",    "mac cosmetics": "EL",
    "bobbi brown":  "EL",    "la mer":       "EL",    "origins":    "EL",
    "loreal":       "LRLCY", "l'oreal":      "LRLCY", "cerave":     "LRLCY",
    "la roche posay":"LRLCY","maybelline":   "LRLCY", "garnier":    "LRLCY",
    "kiehls":       "LRLCY", "lancome":      "LRLCY", "urban decay":"LRLCY",
    "neutrogena":   "JNJ",   "aveeno":       "JNJ",   "clean & clear": "JNJ",
    "olay":         "PG",    "sk-ii":        "PG",    "pantene":    "PG",
    "herbal essences":"PG",  "old spice":    "PG",    "secret":     "PG",
    "dove":         "UL",    "vaseline":     "UL",    "tresemme":   "UL",
    "simple skincare":"UL",  "st ives":      "UL",    "pond's":     "UL",
    "tatcha":       "UL",
    "drunk elephant":"SSDOY","nars":         "SSDOY", "shiseido":   "SSDOY",
    "bare minerals":"SSDOY",
    "honest beauty":"HNST",  "honest company":"HNST",
    "fenty beauty": "LVMHY", "sephora":      "LVMHY",
    "rare beauty":  None,    "charlotte tilbury": None,
    "glossier":     None,    "tower 28":     None,
    "laneige":      None,    "cosrx":        None,    "anua":       None,
    "skin1004":     None,    "beauty of joseon": None,
    "innisfree":    None,    "glow recipe":  None,
    "the ordinary": "EL",    "deciem":       "EL",
    "paula's choice": None,  "inkey list":   None,
    "revolution beauty": None,
    "dyson airwrap":None,    "dyson supersonic": None,

    # ── 👗 WOMEN'S FASHION / RETAIL ────────────────────────────────────────────
    "abercrombie":  "ANF",   "a&f":          "ANF",   "hollister":  "ANF",
    "american eagle":"AEO",  "aerie":        "AEO",
    "urban outfitters":"URBN","anthropologie":"URBN",  "free people":"URBN",
    "revolve":      "RVLV",
    "nordstrom":    "JWN",   "nordstrom rack":"JWN",
    "gap":          "GPS",   "old navy":     "GPS",   "banana republic":"GPS",
    "express":      None,
    "h&m":          "HNNMY",
    "zara":         "IDEXY",
    "skims":        None,    "spanx":        None,
    "alo yoga":     None,    "alo":          None,
    "vuori":        None,
    "fabletics":    None,
    "girlfriend collective": None,
    "quay":         None,

    # ── 👧 TEENS / GEN Z (massive Kaufkraft, oft übersehen) ──────────────────
    "hydroflask":   "HELE",  "hydro flask":  "HELE",
    "owala":        None,
    "stanley quencher": "SWK",
    "ugg mini":     "DECK",  "ugg ultra mini": "DECK",
    "birkenstock":  "BIRK",
    "crocs":        "CROX",
    "golden goose": None,
    "new balance 550": None,
    "adidas samba": "ADDYY", "adidas gazelle": "ADDYY",
    "poppi soda":   "PEP",   # Pepsi hat Poppi übernommen
    "prime":        None,    "prime hydration": None,
    "body doubling": None,
    "bereal":       None,
    "tiktok shop":  None,

    # ── 🧒 KINDER / FAMILIE ────────────────────────────────────────────────────
    "carters":      "CRI",   "carter's":     "CRI",   "oshkosh":    "CRI",
    "hasbro":       "HAS",   "my little pony":"HAS",  "peppa pig":  "HAS",
    "play-doh":     "HAS",   "nerf":         "HAS",   "transformers":"HAS",
    "monopoly":     "HAS",
    "mattel":       "MAT",   "barbie":       "MAT",   "hot wheels":  "MAT",
    "american girl":"MAT",   "monster high": "MAT",   "uno":        "MAT",
    "leapfrog":     None,
    "lovevery":     None,
    "graco":        "NWL",   "newell brands":"NWL",
    "pampers":      "PG",    "luvs":         "PG",    "huggies":    "KMB",
    "kimberly clark":"KMB",
    "gerber":       "NESN",
    "roblox":       "RBLX",
    "fortnite":     None,

    # ── 💊 WOMEN'S HEALTH / WELLNESS ─────────────────────────────────────────
    "ozempic":      "NVO",   "wegovy":       "NVO",   "semaglutide":"NVO",
    "mounjaro":     "LLY",   "tirzepatide":  "LLY",   "zepbound":   "LLY",
    "hims":         "HIMS",  "hers":         "HIMS",  "hims & hers":"HIMS",
    "dexcom":       "DXCM",
    "insulet":      "PODD",  "omnipod":      "PODD",
    "garmin":       "GRMN",
    "oura":         None,    "oura ring":    None,
    "whoop":        None,
    "peloton":      "PTON",
    "theragun":     "AFTR",  "therabody":    "AFTR",
    "eight sleep":  None,
    "ritual":       None,    "olly vitamins":"KO",    "vitafusion": "CHD",

    # ── 🏃 SPORT / OUTDOOR ────────────────────────────────────────────────────
    "nike":         "NKE",   "air max":      "NKE",   "jordan":     "NKE",
    "adidas":       "ADDYY",
    "lululemon":    "LULU",  "lulu":         "LULU",  "align":      "LULU",
    "on running":   "ONON",  "on cloud":     "ONON",
    "hoka":         "DECK",  "ugg":          "DECK",  "teva":       "DECK",
    "skechers":     "SKX",
    "under armour": "UAA",
    "columbia":     "COLM",
    "brooks":       "BRKS",
    "patagonia":    None,    "arcteryx":     "ADDYY",

    # ── 🚗 ELEKTROMOBILITÄT ────────────────────────────────────────────────────
    "tesla":        "TSLA",  "model y":      "TSLA",  "model 3":    "TSLA",
    "cybertruck":   "TSLA",  "powerwall":    "TSLA",
    "rivian":       "RIVN",
    "lucid":        "LCID",
    "nio":          "NIO",
    "byd":          "BYDDY",

    # ── 🥤 GETRÄNKE ────────────────────────────────────────────────────────────
    "celsius":      "CELH",  "celsius energy":"CELH",
    "monster energy":"MNST", "monster":      "MNST",
    "dutch bros":   "BROS",
    "starbucks":    "SBUX",
    "coca-cola":    "KO",    "coke":         "KO",    "fairlife":   "KO",
    "pepsi":        "PEP",   "gatorade":     "PEP",   "liquid iv":  "PEP",
    "liquid death": None,
    "ag1":          None,    "athletic greens": None,

    # ── 🍔 FOOD / RESTAURANT ──────────────────────────────────────────────────
    "chipotle":     "CMG",
    "mcdonald":     "MCD",   "mcdonalds":    "MCD",
    "shake shack":  "SHAK",
    "wingstop":     "WING",
    "sweetgreen":   "SG",
    "cava":         "CAVA",
    "doordash":     "DASH",
    "instacart":    "CART",
    "uber eats":    "UBER",

    # ── 🏠 HOME / LIFESTYLE ────────────────────────────────────────────────────
    "stanley":      "SWK",   "stanley cup":  "SWK",   "stanley tumbler": "SWK",
    "yeti":         "YETI",
    "traeger":      "COOK",
    "roomba":       "IRB",
    "wayfair":      "W",
    "ikea":         None,
    "crate and barrel": None,

    # ── 🛍️ EINZELHANDEL ────────────────────────────────────────────────────────
    "costco":       "COST",
    "target":       "TGT",
    "walmart":      "WMT",
    "tjmaxx":       "TJX",   "marshalls":    "TJX",   "homegoods":  "TJX",
    "ross":         "ROST",
    "five below":   "FIVE",
    "shein":        None,
    "temu":         "PDD",
    "shopify":      "SHOP",

    # ── ✈️ REISE ───────────────────────────────────────────────────────────────
    "airbnb":       "ABNB",
    "uber":         "UBER",
    "booking":      "BKNG",
    "expedia":      "EXPE",
    "royal caribbean":"RCL",
    "carnival":     "CCL",

    # ── 💳 FINTECH ─────────────────────────────────────────────────────────────
    "coinbase":     "COIN",
    "robinhood":    "HOOD",
    "affirm":       "AFRM",
    "klarna":       None,
    "bitcoin":      "MSTR",  "btc":          "MSTR",

    # ── 🎬 ENTERTAINMENT ───────────────────────────────────────────────────────
    "disney":       "DIS",   "disney+":      "DIS",   "pixar":      "DIS",
    "marvel":       "DIS",   "frozen":       "DIS",   "moana":      "DIS",
    "warner":       "WBD",
    "unity":        "U",
    "take-two":     "TTWO",  "gta":          "TTWO",  "gta 6":      "TTWO",
    "ea":           "EA",    "sims":         "EA",

    # ── 🤖 AI / INFRA ──────────────────────────────────────────────────────────
    "supermicro":   "SMCI",
    "broadcom":     "AVGO",
    "tsmc":         "TSM",
    "asml":         "ASML",
}

# ── Demografisches Tagging: Welche Zielgruppe? ────────────────────────────────
# W=Frauen, T=Teens (13-25), K=Kinder (<13), A=Alle, M=Männer (dominant)
BRAND_DEMO: dict[str, list[str]] = {
    # Beauty / Skincare → klassisch von Wall Street übersehen
    "e.l.f": ["W","T"],    "elf beauty": ["W","T"],  "elf cosmetics": ["W","T"],
    "ulta": ["W","T"],     "ulta beauty": ["W","T"],
    "olaplex": ["W"],      "estee lauder": ["W"],    "clinique": ["W"],
    "mac cosmetics": ["W"],"loreal": ["W","T"],      "l'oreal": ["W","T"],
    "cerave": ["W","T"],   "la roche posay": ["W"],  "neutrogena": ["W","T"],
    "olay": ["W"],         "sk-ii": ["W"],           "dove": ["W"],
    "drunk elephant": ["W","T"], "nars": ["W"],      "tatcha": ["W"],
    "honest beauty": ["W","K"],  "fenty beauty": ["W","T"],
    "rare beauty": ["W","T"],    "glossier": ["W","T"],
    "laneige": ["W","T"],  "cosrx": ["W","T"],       "anua": ["W","T"],
    "glow recipe": ["W","T"],    "the ordinary": ["W","T"],
    # Fashion
    "abercrombie": ["T","W"],    "aerie": ["T","W"],
    "american eagle": ["T","W"],"urban outfitters": ["T","W"],
    "anthropologie": ["W"],      "free people": ["W"],
    "revolve": ["W","T"],        "nordstrom": ["W"],
    "gap": ["W","K"],            "old navy": ["W","K"],
    "h&m": ["W","T","K"],        "zara": ["W","T"],
    "skims": ["W"],              "spanx": ["W"],
    "alo yoga": ["W","T"],       "fabletics": ["W"],
    # Teens spezifisch
    "hydroflask": ["T"],         "hydro flask": ["T"],
    "owala": ["T","W"],          "stanley quencher": ["T","W"],
    "crocs": ["T","K"],          "birkenstock": ["T","W"],
    "adidas samba": ["T"],       "adidas gazelle": ["T"],
    "golden goose": ["T","W"],   "poppi soda": ["T"],
    "prime": ["T","K"],          "prime hydration": ["T","K"],
    "ugg mini": ["T","W"],       "ugg ultra mini": ["T","W"],
    # Kinder
    "carters": ["K","W"],        "carter's": ["K","W"],
    "hasbro": ["K"],             "my little pony": ["K"],
    "peppa pig": ["K"],          "barbie": ["K","T","W"],
    "american girl": ["K","T"],  "monster high": ["K","T"],
    "mattel": ["K"],             "hot wheels": ["K"],
    "roblox": ["K","T"],         "minecraft": ["K","T"],
    "lovevery": ["K","W"],       "graco": ["K","W"],
    "pampers": ["K","W"],        "huggies": ["K","W"],
    "gerber": ["K","W"],         "disney": ["K","T","W"],
    "pixar": ["K"],              "frozen": ["K"],       "moana": ["K"],
    "marvel": ["K","T"],         "nintendo": ["K","T"], "pokemon": ["K","T"],
    "fortnite": ["K","T"],
    # Women's Health
    "ozempic": ["W"],            "wegovy": ["W"],       "hers": ["W"],
    "hims & hers": ["W"],        "ritual": ["W"],
    # Lifestyle / Home (Frauen entscheiden 80% der Haushaltskäufe)
    "wayfair": ["W"],            "stanley": ["W","T"],
    "stanley cup": ["W","T"],    "stanley tumbler": ["W","T"],
    "target": ["W"],             "tjmaxx": ["W"],       "marshalls": ["W"],
    "homegoods": ["W"],          "ross": ["W"],         "five below": ["W","K","T"],
    # Sport / Wellness (zunehmend Frauen-dominiert)
    "lululemon": ["W","T"],      "alo": ["W","T"],      "vuori": ["W"],
    "peloton": ["W"],            "on running": ["W","T"],
    "hoka": ["W","T"],
}

def _demo_label(brand: str) -> str:
    """Gibt Emoji-Label für demografische Zugehörigkeit zurück."""
    demos = BRAND_DEMO.get(brand.lower(), [])
    parts = []
    if "W" in demos: parts.append("👩")
    if "T" in demos: parts.append("👧")
    if "K" in demos: parts.append("🧒")
    return " ".join(parts) if parts else ""

def _demo_score_bonus(brand: str) -> float:
    """Bonus für Marken in von Wall Street übersehenen Demografien."""
    demos = BRAND_DEMO.get(brand.lower(), [])
    bonus = 0.0
    if "W" in demos: bonus += 15.0   # Frauen: Wall Street unterschätzt sie systematisch
    if "T" in demos: bonus += 12.0   # Teens: Trendsetter, aber keine Anleger
    if "K" in demos: bonus += 10.0   # Kinder: Eltern kaufen, Analysten messen es nicht
    return bonus

# ── Bullish Demand-Signale ─────────────────────────────────────────────────────
BULLISH_KEYWORDS = [
    # Allgemein
    "sold out", "selling out", "obsessed", "addicted", "can't stop", "cant stop",
    "can't find", "cant find", "impossible to find", "viral", "trending",
    "everywhere", "amazing", "incredible", "game changer", "must have",
    "need this", "love this", "waiting list", "backorder", "pre-order",
    "blew up", "blowing up", "everyone has", "best purchase", "changed my life",
    "buying more", "shortage", "overwhelming", "selling fast", "hooked",
    "restocking", "10/10", "absolutely love", "worth every penny", "underrated",
    "hidden gem", "life changing", "highly recommend", "best ever", "goat",
    "top tier", "slept on", "criminally underrated",
    # Gen Z / Teen Slang
    "fire", "hits different", "bussin", "no cap", "slay", "chef's kiss",
    "it girl", "girl dinner", "that girl", "main character", "vibe check",
    "era", "roman empire", "understood the assignment", "not like other girls",
    "clean girl", "quiet luxury", "old money aesthetic", "dark feminine",
    "cottagecore", "mob wife", "brat", "demure", "mindful",
    "mother", "ate", "ate and left no crumbs",
    # Beauty-spezifisch (Frauen / Teens)
    "holy grail", "dupe", "skin cycling", "slugging", "glass skin",
    "skin barrier", "dewy skin", "no makeup makeup", "blush draping",
    "cloud skin", "strawberry skin", "skincare routine",
    "tiktok made me buy", "tiktok viral", "as seen on tiktok",
    "pinterest worthy", "instagram worthy", "influencer",
    # Kinder / Eltern
    "my kids love", "kids are obsessed", "best toy", "educational",
    "screen free", "montessori", "developmental", "sold at target",
    "christmas gift", "birthday gift", "stocking stuffer",
]
BEARISH_KEYWORDS = [
    "returning", "returned", "disappointed", "terrible", "broken", "defective",
    "recall", "recalled", "lawsuit", "avoid", "stay away", "worst ever",
    "waste of money", "overpriced", "switching away", "stopped using",
    "don't buy", "regret", "refund", "dangerous", "overrated", "scam",
    "garbage", "trash", "horrible", "fake", "knockoff", "greenwashing",
    "microplastics", "toxic", "contaminated",
]

# ── Subreddits aufgeteilt nach Zielgruppe ─────────────────────────────────────
SUBREDDITS_WOMEN = [
    # ── Beauty / Skincare (Megatrend, Wall Street ignoriert das komplett) ──
    "SkincareAddiction", "AsianBeauty", "MakeupAddiction", "beauty",
    "BeautyGuruChatter", "Influenster", "HairDye", "femalehairadvice",
    "ABraThatFits", "30PlusSkinCare", "SkincareAddicts",
    "tretinoin", "acne", "Rosacea", "DermatologyQuestions",
    "HaircareScience", "NaturalHair", "curlyhair", "Haircare",
    "fragrance", "Nails", "RedditLaqueristas", "NailArt",
    "EyelashExtensions", "BeautyBoxes",
    # ── Fashion / Shopping ──
    "femalefashionadvice", "ThriftStoreHauls", "weddingplanning",
    "PetiteFashionAdvice", "capsulewardrobe", "frugalfemalefashion",
    "ThriftFlip", "Depop", "OOAK", "vintage", "VintageFashion",
    "Poshmark", "TheRealReal", "luxuryrepfashion",
    "LushCosmetics", "EltaMD", "CeraVe",
    # ── Lifestyle / Mama ──
    "SAHP", "workingmoms", "beyondthebump", "BabyBumps", "Mommit",
    "breastfeeding", "SingleMoms", "breakingmom", "daddit",
    "TwoXChromosomes", "TheGirlSurvivalGuide", "AskWomen",
    # ── Gesundheit / Wellness ──
    "WomensHealth", "PCOS", "Perimenopause", "Menopause",
    "TTC", "infertility", "EatingDisorders",
    "xxfitness", "loseit", "xxketo", "xxfasting",
    "xxrunning", "yoga", "pilates", "Peloton",
    "bodyweightfitness", "orangetheory", "barre",
    "supplements", "Nootropics", "Meditation", "Mindfulness",
    # ── Home / Decor / Crafts ──
    "HomeDecorating", "femalelivingspace", "malelivingspace",
    "InteriorDesign", "mildlyinteresting", "IKEA", "Etsy",
    "houseplants", "gardening", "UrbanGardening", "succulents",
    "crochet", "knitting", "sewing", "quilting", "Embroidery",
    "DIY", "upcycling", "zerowaste", "ZeroWasteHome",
    "ProjectPan", "sustainability",
    # ── Reisen / Finance ──
    "solotravel", "TravelHacks", "digitalnomad",
    "Frugal", "BuyItForLife", "povertyfinance",
    "FIREyFemmes", "personalfinance", "WomenInTech",
    # ── Gaming / Cozy Games (unterschätzte Zielgruppe!) ──
    "AnimalCrossing", "StardewValley", "Sims4", "PokemonGO",
    "Cozy_Games", "CozyGamers", "GirlGamers", "WomenWhoGames",
    "CasualGaming", "SteamDeck",
    # ── Spiritualität / Community ──
    "witchcraft", "WitchesVsPatriarchy", "astrology",
    "spirituality", "crystals", "tarot",
    # ── Food / Drink Trends ──
    "AirFryer", "Sourdough", "MealPrepSunday", "PlantBasedDiet",
    "vegan", "veganrecipes", "glutenfree", "Coffee", "tea",
    "kombucha", "fermentation", "boba", "starbucks",
]

SUBREDDITS_TEENS = [
    # ── Direkt Teen-Fokus ──
    "teenagers", "GenZ", "college", "highschool",
    "AskTeenGirls", "AskTeenBoys", "Millennials",
    # ── Musik (RIESIG für Gen-Z Kaufentscheidungen) ──
    "taylorswift", "kpop", "bangtan", "BLACKPINK", "twice",
    "kpopthoughts", "kpopfinancials", "kpopmerch",
    "popheads", "popculturechat", "Coachella", "rave",
    "HipHopHeads", "Rap", "indieheads",
    # ── Fashion / Aesthetics ──
    "streetwear", "sneakers", "VSCO", "cottagecore",
    "y2kaesthetic", "softgirl", "fairycore", "DarkAcademia",
    "LightAcademia", "goblincore", "coquette", "balletcore",
    "vintage", "ThriftStoreHauls", "thrifting", "Depop",
    "outfits", "OOTD", "malefashionadvice",
    # ── Beauty ──
    "MakeupAddiction", "SkincareAddiction", "AsianBeauty",
    "BeautyGuruChatter", "TikTokBeauty", "Influenster",
    # ── Social Media / Entertainment ──
    "TikTokCringe", "youtubers", "Twitch", "Streamers",
    "WatchItForThePlot", "TeenMomOGandTeenMom2",
    "ChelseaClinton", "MovieSuggestions",
    # ── Anime / Manga (Gen-Z Mainstream!) ──
    "anime", "manga", "OnePiece", "attackontitan",
    "JujutsuKaisen", "DemonSlayer", "MyHeroAcademia",
    # ── Gaming ──
    "gaming", "Roblox", "Minecraft", "FortNiteBR",
    "PokemonGO", "Pokemon", "LeagueOfLegends",
    "Valorant", "ApexLegends", "NintendoSwitch",
    # ── Food / Drink Trends ──
    "boba", "starbucks", "fastfood", "MukBang", "foodtiktok",
    "energydrinks", "MilkTea",
    # ── Mental Health / Lifestyle ──
    "mentalhealth", "selfimprovement", "Journaling",
    "studyblr", "studytok", "college",
    # ── Finanzen / Nebenjob ──
    "personalfinance", "povertyfinance", "SideHustle",
]

SUBREDDITS_KIDS = [
    # ── Eltern-Sicht (Kaufentscheidungen treffen Eltern!) ──
    "Parenting", "beyondthebump", "Mommit", "toddlers",
    "predaddit", "daddit", "NewParents", "SAHP",
    "infants", "SpecialNeedsParenting", "gifted",
    "Autism", "Aspergers",
    # ── Spielzeug / Bildung ──
    "Lego", "LegoSets", "boardgames", "Toys",
    "Montessori", "homeschool", "unschooling",
    "KidsCrafts", "ArtEducation",
    # ── Kinder-Entertainment ──
    "Disney", "DisneyPlus", "Pixar", "DreamWorks",
    "Nintendo", "NintendoSwitch", "PokemonGO", "Pokemon",
    "Marvel", "StarWars", "HarryPotter",
    "AnimatedFilms", "CartoonNetwork",
    # ── Spielzeug-Brands ──
    "Dolls", "ActionFigures", "LEGO", "HotWheels",
    "Barbie", "PlanetToys",
    # ── Sicherheit / Ernährung ──
    "BabyLedWeaning", "NutritionForKids",
    "ChildSafety", "CarSafety",
]

SUBREDDITS_EARLY = [
    # ── Maximale Reichweite für frühe Signale ──
    "all", "popular", "TrendingOnReddit",
    "BuyItForLife", "Frugal", "Deals", "BlackFriday",
    "TikTokCringe",
    # ── 👩 Frauen ──
    "SkincareAddiction", "AsianBeauty", "MakeupAddiction", "beauty",
    "femalefashionadvice", "ThriftStoreHauls", "Mommit", "beyondthebump",
    "xxfitness", "loseit", "HomeDecorating", "houseplants",
    "fragrance", "Nails", "crochet", "knitting",
    "AnimalCrossing", "StardewValley", "GirlGamers",
    "WomensHealth", "PCOS", "Perimenopause", "Peloton",
    "zerowaste", "Etsy", "solotravel",
    # ── 👧 Teens ──
    "teenagers", "GenZ", "streetwear", "sneakers",
    "BeautyGuruChatter", "popheads", "popculturechat",
    "taylorswift", "kpop", "bangtan",
    "y2kaesthetic", "cottagecore", "DarkAcademia",
    "anime", "Roblox", "PokemonGO",
    "boba", "energydrinks", "MilkTea",
    # ── 🧒 Kinder / Eltern ──
    "Parenting", "toddlers", "daddit",
    "Lego", "Disney", "Pokemon", "Marvel",
    # ── Sport / Fitness ──
    "fitness", "running", "yoga", "pilates",
    "bodyweightfitness", "crossfit", "orangetheory",
    # ── Food / Drink Trends ──
    "EatCheapAndHealthy", "MealPrepSunday",
    "AirFryer", "Sourdough", "PlantBasedDiet", "vegan",
    "Coffee", "kombucha", "starbucks", "boba",
    # ── Home / Interior ──
    "InteriorDesign", "IKEA", "femalelivingspace",
    "gardening", "succulents",
    # ── Gaming / Tech (alle Gruppen) ──
    "gaming", "NintendoSwitch", "Cozy_Games",
    "pcmasterrace", "hardware",
    # ── Finance ──
    "personalfinance", "investing", "wallstreetbets",
    "SideHustle", "povertyfinance",
    # ── Nischen mit hohem Signal ──
    "Etsy", "ProductReviews", "Wishlist",
    "camping", "hiking", "outdoors",
]

SUBREDDITS_CLASSIC = [
    "all", "popular",
    # Beauty / Fashion
    "SkincareAddiction", "femalefashionadvice", "MakeupAddiction",
    "AsianBeauty", "fragrance", "streetwear", "sneakers",
    # Shopping / Deals
    "BuyItForLife", "Frugal", "Deals", "Etsy",
    # Fitness / Health
    "fitness", "running", "xxfitness", "loseit",
    "yoga", "Peloton", "bodyweightfitness",
    # Teens / Gen-Z
    "teenagers", "GenZ", "kpop", "taylorswift", "anime",
    # Familie
    "Parenting", "Mommit", "beyondthebump", "toddlers",
    # Gaming
    "gaming", "NintendoSwitch", "Cozy_Games",
    "AnimalCrossing", "StardewValley", "GirlGamers",
    # Food Trends
    "AirFryer", "Sourdough", "Coffee", "boba", "vegan",
    # Home
    "HomeDecorating", "InteriorDesign", "houseplants", "IKEA",
    # Finance
    "personalfinance", "investing",
]

# ══════════════════════════════════════════════════════════════════════════════
# DATEN-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

def _find_brands(text: str) -> list[str]:
    """
    Findet Marken-Erwähnungen im Text.
    Verwendet Wortgrenzen für Einzelwort-Brands (verhindert false positives wie
    'era' → 'camera', 'ring' → 'earring', 'elf' → 'shelf').
    Multi-Wort-Brands (z.B. 'apple watch', 'la roche posay') nutzen Substring-Matching.
    """
    text_lower = text.lower()
    found = []
    for brand in BRAND_TICKER:
        if " " in brand:
            # Multi-Wort Brand: Substring reicht (false positives unwahrscheinlich)
            if brand in text_lower:
                found.append(brand)
        else:
            # Einzelwort: Wortgrenze erforderlich — verhindert 'era'∈'camera', 'elf'∈'shelf'
            if re.search(r"\b" + re.escape(brand) + r"\b", text_lower):
                found.append(brand)
    return found


def _kw_in(kw: str, text: str) -> bool:
    """Prüft ob Keyword im Text vorkommt — mit Wortgrenzen für kurze Wörter."""
    if len(kw) <= 4:
        # Kurze Keywords: Wortgrenzen, z.B. 'era' nicht in 'camera'
        return bool(re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE))
    # Längere Keywords: Substring reicht (Geschwindigkeit)
    return kw in text.lower()


@st.cache_data(ttl=1800, show_spinner=False)
def _google_trending(country: str = "united_states") -> list[str]:
    """Aktuelle Google Trending Searches (pytrends)."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
        df = pt.trending_searches(pn=country)
        return df[0].tolist()[:30]
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _reddit_scan(
    subreddits: tuple[str, ...],
    min_score: int,
    sort_modes: tuple[str, ...] = ("hot",),
    limit: int = 30,
) -> list[dict]:
    """
    Scannt Reddit-Posts auf Produkt-Erwähnungen.
    sort_modes: "hot", "rising", "new", "top" (kombiniert für bessere Früherkennung)
    """
    import requests
    posts: list[dict] = []
    seen: set[str] = set()
    headers = {"User-Agent": "StillhalterApp/2.1"}

    for sub in subreddits:
        for sort in sort_modes:
            try:
                # Bei "new"/"rising" niedrigeren Score-Filter anwenden
                effective_min = max(1, min_score // 20) if sort in ("new", "rising") else min_score
                url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}"
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                for child in r.json().get("data", {}).get("children", []):
                    p = child.get("data", {})
                    pid = p.get("id", "")
                    if pid in seen or p.get("score", 0) < effective_min:
                        continue
                    seen.add(pid)
                    title = p.get("title", "")
                    text  = p.get("selftext", "")[:600]
                    combined = title + " " + text
                    brands = _find_brands(combined)
                    if not brands:
                        continue
                    bull = sum(1 for kw in BULLISH_KEYWORDS if _kw_in(kw, combined))
                    bear = sum(1 for kw in BEARISH_KEYWORDS if _kw_in(kw, combined))
                    posts.append({
                        "id":        pid,
                        "title":     title,
                        "score":     p.get("score", 0),
                        "comments":  p.get("num_comments", 0),
                        "subreddit": p.get("subreddit", sub),
                        "sort":      sort,
                        "url":       "https://reddit.com" + p.get("permalink", ""),
                        "brands":    brands,
                        "bull":      bull,
                        "bear":      bear,
                        "text":      text[:300],
                    })
            except Exception:
                continue
    return posts


@st.cache_data(ttl=600, show_spinner=False)
def _stocktwits_trending() -> list[dict]:
    """
    StockTwits Trending Tickers — zeigt welche Aktien gerade viral diskutiert werden.
    Kostenlose API, kein Key erforderlich.
    """
    import requests
    try:
        r = requests.get(
            "https://api.stocktwits.com/api/2/trending/symbols.json",
            timeout=10,
        )
        if r.status_code != 200:
            return []
        symbols = r.json().get("symbols", [])
        return [
            {
                "ticker":  s.get("symbol", ""),
                "title":   s.get("title", ""),
                "watchlist": s.get("watchlist_count", 0),
            }
            for s in symbols
        ]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def _product_hunt_feed() -> list[dict]:
    """
    Product Hunt RSS-Feed — neue virale Produkte/Startups.
    Kostenlos, kein API-Key nötig.
    """
    import requests, xml.etree.ElementTree as ET
    try:
        r = requests.get(
            "https://www.producthunt.com/feed",
            headers={"User-Agent": "StillhalterApp/2.1"},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()[:300]
            link  = (item.findtext("link") or "").strip()
            combined = title + " " + desc
            brands = _find_brands(combined)
            bull   = sum(1 for kw in BULLISH_KEYWORDS if _kw_in(kw, combined))
            items.append({
                "title":  title,
                "desc":   desc,
                "link":   link,
                "brands": brands,
                "bull":   bull,
            })
        return items
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _hackernews_trending() -> list[dict]:
    """
    Hacker News Top Stories — Tech-Trend-Frühwarnung.
    Komplett kostenlos, offizielle Firebase-API.
    """
    import requests
    try:
        top_ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10,
        ).json()[:30]
        stories = []
        for sid in top_ids:
            try:
                s = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=8,
                ).json()
                if not s or s.get("type") != "story":
                    continue
                title = s.get("title", "")
                url   = s.get("url", f"https://news.ycombinator.com/item?id={sid}")
                score = s.get("score", 0)
                brands = _find_brands(title)
                bull   = sum(1 for kw in BULLISH_KEYWORDS if _kw_in(kw, title))
                stories.append({
                    "title":  title,
                    "url":    url,
                    "score":  score,
                    "brands": brands,
                    "bull":   bull,
                })
            except Exception:
                continue
        return stories
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _reddit_comments(post_id: str, limit: int = 30) -> list[str]:
    """Lädt die Top-Kommentare eines Reddit-Posts."""
    import requests
    try:
        url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}&depth=1"
        r = requests.get(url, headers={"User-Agent": "StillhalterApp/2.1"}, timeout=10)
        if r.status_code != 200:
            return []
        comments = []
        for item in r.json():
            for child in item.get("data", {}).get("children", []):
                body = child.get("data", {}).get("body", "")
                if body and body != "[deleted]":
                    comments.append(body[:400])
        return comments[:30]
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _stock_info(ticker: str) -> dict:
    """Kurs + 30/90-Tage-Rendite via yfinance."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty or len(hist) < 5:
            return {}
        cur = float(hist["Close"].iloc[-1])
        p30 = float(hist["Close"].iloc[max(-22, -len(hist))])
        p90 = float(hist["Close"].iloc[0])
        r30 = (cur - p30) / p30 * 100
        r90 = (cur - p90) / p90 * 100

        if r90 > 35:
            label, color = "Stark eingepreist 🔴", "#ef4444"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Markt kennt den Trend bereits"
        elif r90 > 15:
            label, color = "Teilweise eingepreist 🟡", "#f59e0b"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Trend bekannt, noch Upside möglich"
        elif r90 > 0:
            label, color = "Kaum eingepreist ✅", "#22c55e"
            hint = f"Aktie nur +{r90:.0f}% — Trend noch nicht vollständig reflektiert"
        elif r90 > -15:
            label, color = "Nicht eingepreist ✅✅", "#22c55e"
            hint = f"Aktie seitwärts trotz Trend — frühes Signal!"
        else:
            label, color = "Gegenläufig 📉", "#8b5cf6"
            hint = f"Aktie -{abs(r90):.0f}% trotz Trend — Konträr-Signal prüfen"

        return {
            "price": cur, "r30": r30, "r90": r90,
            "label": label, "color": color, "hint": hint,
        }
    except Exception:
        return {}


def _aggregate_brands(
    posts: list[dict],
    trending_google: list[str],
    hn_stories: list[dict],
    ph_items: list[dict],
) -> list[dict]:
    """Aggregiert Marken-Erwähnungen aus allen Quellen und berechnet Trend-Score."""
    from collections import defaultdict
    brand_data: dict[str, dict] = defaultdict(lambda: {
        "posts": [], "subreddits": set(), "bull": 0, "bear": 0,
        "google": False, "hn": False, "ph": False,
        "reddit_score_sum": 0, "reddit_rising": 0,
    })

    # Reddit-Daten
    for post in posts:
        for brand in post["brands"]:
            bd = brand_data[brand]
            bd["posts"].append(post)
            bd["subreddits"].add(post["subreddit"])
            bd["bull"] += post["bull"]
            bd["bear"] += post["bear"]
            bd["reddit_score_sum"] += post["score"]
            if post.get("sort") in ("rising", "new"):
                bd["reddit_rising"] += 1

    # Google Trends ergänzen
    for term in trending_google:
        term_lower = term.lower()
        for brand in BRAND_TICKER:
            if brand in term_lower or term_lower in brand:
                brand_data[brand]["google"] = True

    # Hacker News ergänzen
    for story in hn_stories:
        for brand in story.get("brands", []):
            brand_data[brand]["hn"] = True
            if not any(p["title"] == story["title"] for p in brand_data[brand]["posts"]):
                brand_data[brand]["posts"].append({
                    "id": f"hn_{story.get('score',0)}",
                    "title": story["title"],
                    "score": story.get("score", 0),
                    "comments": 0,
                    "subreddit": "HackerNews",
                    "sort": "top",
                    "url": story.get("url", ""),
                    "brands": story["brands"],
                    "bull": story.get("bull", 0),
                    "bear": 0,
                    "text": "",
                })
            brand_data[brand]["bull"] += story.get("bull", 0)
            brand_data[brand]["reddit_score_sum"] += story.get("score", 0) * 2

    # Product Hunt ergänzen
    for item in ph_items:
        for brand in item.get("brands", []):
            brand_data[brand]["ph"] = True
            brand_data[brand]["bull"] += item.get("bull", 0) + 2  # PH = Bonus

    # Ticker zuordnen + Score berechnen
    results = []
    for brand, bd in brand_data.items():
        ticker = BRAND_TICKER.get(brand)
        n_posts = len(bd["posts"])
        if n_posts == 0:
            continue
        total_sig = bd["bull"] + bd["bear"]
        net_sentiment = (bd["bull"] - bd["bear"]) / max(total_sig, 1) * 100 if total_sig > 0 else 0
        demo_bonus = _demo_score_bonus(brand)
        trend_score = (
            n_posts * 10
            + bd["reddit_score_sum"] / 500
            + bd["bull"] * 5
            + bd["reddit_rising"] * 15          # Rising-Posts = stärkerer Bonus
            + (20 if bd["google"] else 0)
            + (15 if bd["hn"] else 0)
            + (10 if bd["ph"] else 0)
            + demo_bonus                         # 👩👧🧒 Wall-Street-Blind-Spot-Bonus
        )
        demo_lbl = _demo_label(brand)
        results.append({
            "brand":         brand,
            "ticker":        ticker,
            "n_posts":       n_posts,
            "subreddits":    sorted(bd["subreddits"]),
            "bull":          bd["bull"],
            "bear":          bd["bear"],
            "net_sentiment": round(net_sentiment, 1),
            "google":        bd["google"],
            "hn":            bd["hn"],
            "ph":            bd["ph"],
            "rising":        bd["reddit_rising"],
            "trend_score":   round(trend_score, 1),
            "demo":          BRAND_DEMO.get(brand.lower(), []),
            "demo_label":    demo_lbl,
            "top_posts":     sorted(bd["posts"], key=lambda x: x["score"], reverse=True)[:5],
        })
    return sorted(results, key=lambda x: x["trend_score"], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# UI — HEADER
# ══════════════════════════════════════════════════════════════════════════════
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("auto", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">Sentiment Analyse</div>'
        '<div class="sc-page-subtitle">'
        'Chris Camillo Social Arbitrage · Virale Trends automatisch entdecken · '
        'Reddit · Google Trends · StockTwits · Product Hunt · Hacker News · '
        '<span style="color:#f0a0c0">👩 Frauen</span> · '
        '<span style="color:#c0a0f0">👧 Teens</span> · '
        '<span style="color:#a0c0f0">🧒 Kinder</span> — von Wall Street übersehen</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Erklärung ──────────────────────────────────────────────────────────────────
with st.expander("💡 **Wie funktioniert die Sentiment Analyse? · Alle Datenquellen**", expanded=False):
    st.markdown("""
    **Chris Camillo** investiert nach der **„Social Arbitrage"** Methode:
    Erkenne Produkt-Trends auf Social Media, **bevor** die Wall Street davon weiß.

    ### 👩👧🧒 Der entscheidende Blind Spot von Wall Street
    > *"Die meisten Analysten sind Männer mittleren Alters. Sie sehen nicht was ihre Töchter,
    Frauen und Mütter kaufen — aber genau dort entstehen die besten Trends."*

    | Zielgruppe | Kaufkraft | Wall Street Aufmerksamkeit | Opportunity |
    |------------|-----------|--------------------------|-------------|
    | **👩 Frauen 25-45** | 80% aller Haushaltskäufe | Sehr gering | ⭐⭐⭐⭐⭐ |
    | **👧 Teens (Gen Z)** | $360 Mrd./Jahr USA | Gering | ⭐⭐⭐⭐ |
    | **🧒 Kinder (via Eltern)** | $1 Billion Familienausgaben | Sehr gering | ⭐⭐⭐⭐ |

    **Beispiele:** e.l.f. Beauty (ELF) +800% · Abercrombie (ANF) +500% · Celsius (CELH) +2000% ·
    On Running (ONON) +300% — alle durch Frauen/Teens getrieben, alle von Analysten zu spät erkannt.

    ### Datenquellen im Überblick

    | Quelle | Was wird gescannt | Stärke |
    |--------|------------------|--------|
    | **Reddit Hot** | Beliebte Posts in Consumer-Subreddits | Bestätigte Trends, hohe Reichweite |
    | **Reddit Rising** | Posts die gerade an Upvotes gewinnen | **Frühe Signale!** Trend entsteht gerade |
    | **Reddit New** | Neueste Posts | Sehr frühe Signale, mehr Rauschen |
    | **Google Trends** | Trending Searches in Echtzeit | Massenmarkt-Nachfrage |
    | **StockTwits** | Trending Aktien der Community | Direkte Aktien-Momentum-Signale |
    | **Product Hunt** | Neu lansierte Produkte/Startups | Früheste Produktentdeckungen |
    | **Hacker News** | Tech-Community Top-Stories | Tech-Trends früh erkennen |

    ### Ablauf
    | Schritt | Was passiert |
    |---|---|
    | 1️⃣ Multi-Scan | Alle 7 Quellen werden gleichzeitig ausgewertet |
    | 2️⃣ Extrakt | App findet Marken- und Produkt-Erwähnungen |
    | 3️⃣ Mapping | Jedes Produkt wird einer börsennotierten Aktie zugeordnet |
    | 4️⃣ Einpreisung | Kursperformance zeigt, ob der Markt den Trend schon kennt |

    ### Beste Signale (Chris Camillo Methode)
    > *"sold out", "obsessed", "can't find it", "everywhere", "waiting list", "blew up"*

    **Kaum eingepreist + Bullish Sentiment = frühes Long-Signal** ✅
    **Stark eingepreist = Trend bekannt, Upside begrenzt** ⚠️

    ### Tipp: Early Detection Modus
    Aktiviere **Rising + New Posts** für früheste Trend-Signale — mehr Rauschen,
    aber Trends werden 2–5 Tage früher erkannt als über Hot-Posts.
    """)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_auto, tab_manual, tab_stocktwits = st.tabs([
    "🔍 Auto-Scan (alle Quellen)",
    "🔎 Manuell suchen",
    "📊 StockTwits Trending",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: AUTO-SCAN
# ══════════════════════════════════════════════════════════════════════════════
with tab_auto:

    # ── Scan-Einstellungen ─────────────────────────────────────────────────────
    with st.expander("⚙️ **Scan-Einstellungen**", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            scan_mode = st.radio(
                "Scan-Modus",
                ["🎯 Klassisch (Hot)", "🚀 Early Detection (Hot + Rising)", "🔬 Maximale Breite (Hot + Rising + New)"],
                index=1,
                help="Early Detection findet Trends 2–5 Tage früher als Klassisch, aber mit mehr Rauschen",
            )
            if "Klassisch" in scan_mode:
                sort_modes = ("hot",)
            elif "Early" in scan_mode:
                sort_modes = ("hot", "rising")
            else:
                sort_modes = ("hot", "rising", "new")

            st.markdown("**Zielgruppen-Fokus**")
            demo_women = st.checkbox("👩 Frauen (Beauty, Fashion, Family)", value=True)
            demo_teens = st.checkbox("👧 Teens / Gen Z (Trends, Style)", value=True)
            demo_kids  = st.checkbox("🧒 Kinder / Eltern (Spielzeug, Baby)", value=True)
            demo_all   = st.checkbox("👔 Allgemein / Tech / Männer", value=True)

            # Subreddits dynamisch zusammenstellen
            sub_pool: list[str] = ["all", "popular", "Frugal", "Deals"]
            if demo_women: sub_pool += SUBREDDITS_WOMEN
            if demo_teens: sub_pool += SUBREDDITS_TEENS
            if demo_kids:  sub_pool += SUBREDDITS_KIDS
            if demo_all:   sub_pool += ["gaming", "pcmasterrace", "hardware", "personalfinance", "investing", "wallstreetbets", "fitness", "running"]
            sub_pool = list(dict.fromkeys(sub_pool))  # Deduplizieren

        with sc2:
            all_subs = list(dict.fromkeys(
                SUBREDDITS_EARLY + SUBREDDITS_WOMEN + SUBREDDITS_TEENS + SUBREDDITS_KIDS
            ))
            selected_subs = st.multiselect(
                "Subreddits (manuell anpassen)",
                all_subs,
                default=sub_pool[:20],
                help="Wird automatisch aus Zielgruppen-Auswahl befüllt — kann überschrieben werden",
            )
            min_score = st.number_input(
                "Min. Reddit Upvotes (Hot)", 5, 5000, 25, step=10,
                help="Nur Hot-Posts mit mind. X Upvotes. Für Rising/New wird 1/20 angewendet. Niedrig = mehr frühe Signale.",
            )

        with sc3:
            trends_country = st.selectbox(
                "Google Trends Land",
                ["united_states", "germany", "united_kingdom", "canada", "australia"],
                help="Für welches Land sollen Google Trending Searches geladen werden?",
            )
            use_hn  = st.checkbox("🔶 Hacker News einbeziehen", value=True)
            use_ph  = st.checkbox("🔸 Product Hunt einbeziehen", value=True)

            if any([demo_women, demo_teens, demo_kids]):
                active_demos = []
                if demo_women: active_demos.append("👩 Frauen")
                if demo_teens: active_demos.append("👧 Teens")
                if demo_kids:  active_demos.append("🧒 Kinder")
                st.info(
                    f"**Wall-Street-Blind-Spot aktiv:** {' · '.join(active_demos)}\n\n"
                    f"Diese Zielgruppen erhalten Score-Bonus da Analysten sie systematisch unterschätzen.",
                    icon="💡",
                )

    # ── Scan-Button ─────────────────────────────────────────────────────────────
    scan_col, rescan_col, info_col = st.columns([2, 2, 5])
    with scan_col:
        scan_btn = st.button(
            "🔍 Alle Quellen scannen",
            type="primary",
            use_container_width=True,
        )
    with rescan_col:
        # Neuscan-Button: löscht Cache und erzwingt frische Daten
        force_rescan = st.button(
            "🔄 Neu scannen (Cache leeren)",
            use_container_width=True,
            help="Löscht gecachte Daten und holt frische Ergebnisse von allen Quellen.",
            disabled="sentiment_results" not in st.session_state,
        )
    with info_col:
        st.markdown(
            "<div style='padding-top:8px;font-size:0.78rem;color:#555'>"
            "Reddit · Google Trends · StockTwits · Product Hunt · Hacker News "
            "· Ergebnisse 15 Min. gecacht · Neu Scannen = Cache leeren"
            "</div>",
            unsafe_allow_html=True,
        )

    # Cache leeren wenn Force-Rescan geklickt
    if force_rescan:
        _reddit_scan.clear()
        _google_trending.clear()
        _hackernews_trending.clear()
        _product_hunt_feed.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("sentiment_"):
                del st.session_state[k]
        st.rerun()

    if not scan_btn and "sentiment_results" not in st.session_state:
        st.info(
            "👆 **'Alle Quellen scannen'** klicken — App scannt automatisch alle "
            "Social-Media-Quellen und findet virale Produkte mit Aktien-Ticker.",
            icon="🧭",
        )

    else:
        # ── Scan ausführen ─────────────────────────────────────────────────────
        if scan_btn or "sentiment_results" not in st.session_state:
            _progress = st.progress(0, text="📡 Scanne Reddit …")
            reddit_posts = _reddit_scan(
                tuple(selected_subs if selected_subs else ["all", "BuyItForLife"]),
                min_score,
                sort_modes=tuple(sort_modes),
            )
            _progress.progress(30, text="📈 Lade Google Trends …")
            google_trends = _google_trending(trends_country)
            _progress.progress(55, text="🔶 Hacker News …")
            hn_stories = _hackernews_trending() if use_hn else []
            _progress.progress(70, text="🔸 Product Hunt …")
            ph_items = _product_hunt_feed() if use_ph else []
            _progress.progress(90, text="🧮 Aggregiere Ergebnisse …")
            results = _aggregate_brands(reddit_posts, google_trends, hn_stories, ph_items)
            _progress.progress(100, text="✅ Fertig!")
            _progress.empty()

            st.session_state["sentiment_results"]      = results
            st.session_state["sentiment_google"]       = google_trends
            st.session_state["sentiment_reddit_count"] = len(reddit_posts)
            st.session_state["sentiment_hn_count"]     = len(hn_stories)
            st.session_state["sentiment_ph_count"]     = len(ph_items)
            st.session_state["sentiment_scan_time"]    = datetime.now().strftime("%H:%M")

        results       = st.session_state.get("sentiment_results", [])
        google_trends = st.session_state.get("sentiment_google", [])
        reddit_count  = st.session_state.get("sentiment_reddit_count", 0)
        hn_count      = st.session_state.get("sentiment_hn_count", 0)
        ph_count      = st.session_state.get("sentiment_ph_count", 0)
        scan_time     = st.session_state.get("sentiment_scan_time", "–")

        # ── Scan-Info ──────────────────────────────────────────────────────────
        mc = st.columns(5)
        mc[0].metric("Reddit Posts",   reddit_count)
        mc[1].metric("Google Trends",  len(google_trends))
        mc[2].metric("HN Stories",     hn_count)
        mc[3].metric("PH Launches",    ph_count)
        mc[4].metric("Trend-Produkte", len(results))

        if not results:
            st.warning(
                "**Keine Trend-Produkte gefunden.**\n\n"
                "**Mögliche Ursachen & Lösungen:**\n"
                "- 🔽 **Min. Upvotes senken** (aktuell zu hoch — versuche 10–50)\n"
                "- 📋 **Mehr Subreddits** hinzufügen (z.B. `all`, `popular`)\n"
                "- 🚀 **Early Detection Modus** aktivieren (Rising + New Posts)\n"
                "- ⏰ **Tageszeit**: Morgens (US-Zeit) gibt es mehr aktive Posts\n"
                "- 🔎 **Manuell suchen** (Tab 2) für gezieltes Trend-Tracking",
                icon="⚠️",
            )

        else:
            # ── Google Trends ──────────────────────────────────────────────────
            if google_trends:
                with st.expander(f"📈 Google Trending Searches ({len(google_trends)})", expanded=False):
                    gt_cols = st.columns(5)
                    for i, term in enumerate(google_trends):
                        matched = [b for b in BRAND_TICKER if b in term.lower() or term.lower() in b]
                        badge = f" → **{BRAND_TICKER[matched[0]]}**" if matched else ""
                        gt_cols[i % 5].markdown(f"· {term}{badge}")

            # ── Filter ────────────────────────────────────────────────────────
            f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
            with f1:
                show_only_ticker = st.checkbox(
                    "Nur mit Aktien-Ticker",
                    value=True,
                    help="Nur Produkte anzeigen die einem börsennotierten Unternehmen zugeordnet sind",
                )
            with f2:
                show_only_bullish = st.checkbox(
                    "Nur Bullish-Signale",
                    value=False,
                )
            with f3:
                show_only_not_priced = st.checkbox(
                    "Nur kaum eingepreist",
                    value=False,
                    help="Aktie noch nicht stark gestiegen — beste Einstiegs-Chance",
                )
            with f4:
                demo_filter = st.multiselect(
                    "👩👧🧒 Zielgruppe",
                    ["👩 Frauen", "👧 Teens", "🧒 Kinder"],
                    default=[],
                    help="Nur Trends dieser demografischen Gruppe zeigen",
                    placeholder="Alle Gruppen",
                )

            filtered = results
            if show_only_ticker:
                filtered = [r for r in filtered if r["ticker"]]
            if show_only_bullish:
                filtered = [r for r in filtered if r["bull"] > r["bear"]]
            if demo_filter:
                demo_map = {"👩 Frauen": "W", "👧 Teens": "T", "🧒 Kinder": "K"}
                wanted = {demo_map[d] for d in demo_filter}
                filtered = [r for r in filtered if wanted & set(r.get("demo", []))]

            # Einpreisung laden wenn benötigt
            if show_only_not_priced:
                not_priced = []
                for r in filtered:
                    if r["ticker"]:
                        si = _stock_info(r["ticker"])
                        if si and si.get("r90", 999) <= 15:
                            not_priced.append(r)
                    else:
                        not_priced.append(r)
                filtered = not_priced

            st.markdown(
                f"<div style='font-size:0.78rem;color:#555;margin:8px 0'>"
                f"📦 <b>{len(filtered)}</b> Trend-Produkte · Scan {scan_time} Uhr"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Ergebnis-Karten ────────────────────────────────────────────────
            for i, item in enumerate(filtered[:25]):
                brand  = item["brand"].title()
                ticker = item["ticker"]
                score  = item["trend_score"]
                nsubs  = len(item["subreddits"])
                bull   = item["bull"]
                bear   = item["bear"]
                net    = item["net_sentiment"]
                rising = item.get("rising", 0)

                # Quellen-Badges
                source_badges = []
                if item.get("google"):  source_badges.append("📈 Google")
                if item.get("hn"):      source_badges.append("🔶 HackerNews")
                if item.get("ph"):      source_badges.append("🔸 ProductHunt")
                if rising > 0:          source_badges.append(f"🚀 {rising}× Rising")

                # Stock-Daten
                sinfo: dict = _stock_info(ticker) if ticker else {}

                # Badge HTML
                ticker_badge = (
                    f'<span style="background:#d4a843;color:#000;font-weight:700;'
                    f'font-size:0.75rem;padding:2px 8px;border-radius:12px;margin-left:6px">'
                    f'{ticker}</span>'
                    if ticker else
                    '<span style="color:#444;font-size:0.75rem;margin-left:6px">kein Ticker</span>'
                )
                price_badge = ""
                if sinfo:
                    r90_color = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
                    r90_sign  = "+" if sinfo["r90"] >= 0 else ""
                    price_badge = (
                        f'<span style="background:#111;border:1px solid #333;border-radius:20px;'
                        f'padding:2px 10px;font-size:0.78rem;color:#f0f0f0;margin-left:8px">'
                        f'${sinfo["price"]:.2f} '
                        f'<span style="color:{r90_color}">{r90_sign}{sinfo["r90"]:.0f}%</span>'
                        f'<span style="color:#444;font-size:0.68rem"> 90T</span>'
                        f'</span>'
                    )

                demo_lbl   = item.get("demo_label", "")
                expander_icon = "🔥" if score > 60 else ("⚡" if rising > 0 else "📦")
                src_str = " · ".join(source_badges) if source_badges else ""
                ticker_str = f"  [Aktie: {ticker}]" if ticker else "  [kein Ticker]"
                demo_str = f"  {demo_lbl}" if demo_lbl else ""

                with st.expander(
                    f"{expander_icon}{demo_str}  Produkt: {brand}{ticker_str}"
                    f"  ·  Score {score:.0f}  ·  {item['n_posts']} Posts"
                    + (f"  ·  {src_str}" if src_str else ""),
                    expanded=False,
                ):
                    # Demo-Badge prominent
                    demo_html = ""
                    for code, emoji, label, color in [
                        ("W","👩","Frauen","#f0a0c0"),
                        ("T","👧","Teens","#c0a0f0"),
                        ("K","🧒","Kinder","#a0c0f0"),
                    ]:
                        if code in item.get("demo", []):
                            demo_html += (
                                f'<span style="background:#1a0e1a;border:1px solid {color}44;'
                                f'color:{color};font-size:0.72rem;padding:2px 8px;'
                                f'border-radius:10px;margin-right:4px">'
                                f'{emoji} {label} — Wall-Street-Blind-Spot</span>'
                            )

                    st.markdown(
                        f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;'
                        f'margin-bottom:6px">'
                        f'<span style="font-size:1.05rem;font-weight:700;color:#f0f0f0">{brand}</span>'
                        f'{ticker_badge}{price_badge}'
                        + "".join(
                            f'<span style="background:#1a1a2a;color:#818cf8;font-size:0.7rem;'
                            f'padding:1px 7px;border-radius:10px;margin-left:4px">{b}</span>'
                            for b in source_badges
                        )
                        + f'</div>'
                        + (f'<div style="margin-bottom:8px">{demo_html}</div>' if demo_html else ""),
                        unsafe_allow_html=True,
                    )

                    # ── TREND-BESCHREIBUNG (Hauptfokus — WAS ist der Trend?) ──
                    # Aus den Top-Posts automatisch einen Trend-Satz ableiten
                    top_titles = [p["title"] for p in item["top_posts"][:3]]
                    bull_kws_found = [kw for kw in BULLISH_KEYWORDS
                                      if any(_kw_in(kw, t) for t in top_titles)][:4]

                    trend_summary_parts = []
                    if bull_kws_found:
                        trend_summary_parts.append(
                            f"Menschen beschreiben es als: "
                            + ", ".join(f'<b style="color:#22c55e">"{kw}"</b>' for kw in bull_kws_found)
                        )
                    if rising > 0:
                        trend_summary_parts.append(f"📈 {rising} Posts gerade am Aufsteigen (Rising)")
                    if item.get("google"):
                        trend_summary_parts.append("🔍 Aktuell in Google Trending Searches")
                    subreddit_context = ", ".join(
                        f"r/{s}" for s in item["subreddits"][:4] if s != "HackerNews"
                    )
                    if subreddit_context:
                        trend_summary_parts.append(f"Diskutiert in: {subreddit_context}")

                    if trend_summary_parts:
                        st.markdown(
                            f'<div style="background:#0a0e0a;border:1px solid #1a3a1a;'
                            f'border-left:3px solid #22c55e;border-radius:8px;'
                            f'padding:10px 14px;margin-bottom:10px">'
                            f'<div style="font-size:0.72rem;color:#555;text-transform:uppercase;'
                            f'letter-spacing:0.08em;margin-bottom:5px">🔍 Was ist der Trend?</div>'
                            + "".join(
                                f'<div style="font-size:0.82rem;color:#ccc;margin-top:3px">· {p}</div>'
                                for p in trend_summary_parts
                            )
                            + f'</div>',
                            unsafe_allow_html=True,
                        )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Quellen/Posts",    item["n_posts"])
                    m2.metric("Bullish Signale",  bull)
                    m3.metric("Bearish Signale",  bear)
                    m4.metric("Net Sentiment",    f"{net:+.0f}")

                    # Einpreisung
                    if sinfo:
                        r30c = "#22c55e" if sinfo["r30"] >= 0 else "#ef4444"
                        r90c = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
                        st.markdown(
                            f'<div style="background:#0a0a0a;border:1px solid {sinfo["color"]}33;'
                            f'border-left:3px solid {sinfo["color"]};border-radius:8px;'
                            f'padding:10px 14px;margin:8px 0">'
                            f'<div style="font-size:0.85rem;font-weight:700;color:{sinfo["color"]};'
                            f'margin-bottom:4px">📊 Einpreisung: {sinfo["label"]}</div>'
                            f'<div style="font-size:0.78rem;color:#888">{sinfo["hint"]}</div>'
                            f'<div style="font-size:0.75rem;color:#555;margin-top:4px">'
                            f'30 Tage: <span style="color:{r30c}">{sinfo["r30"]:+.1f}%</span>'
                            f' &nbsp;|&nbsp; '
                            f'90 Tage: <span style="color:{r90c}">{sinfo["r90"]:+.1f}%</span>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                    # Quellen
                    subs_html = " · ".join(f"r/{s}" if s != "HackerNews" else "HN" for s in item["subreddits"][:6])
                    st.markdown(
                        f'<div style="font-size:0.75rem;color:#444;margin-bottom:8px">'
                        f'Gefunden in: {subs_html}</div>',
                        unsafe_allow_html=True,
                    )

                    # Posts
                    top_posts = item["top_posts"]
                    if top_posts:
                        st.markdown("**📰 Quellen-Posts:**")
                        for p in top_posts[:4]:
                            title_hl = p["title"]
                            for kw in BULLISH_KEYWORDS:
                                if _kw_in(kw, title_hl):
                                    # Wortgrenze beachten beim Hervorheben
                                    title_hl = re.sub(
                                        r"\b" + re.escape(kw) + r"\b",
                                        f'<b style="color:#22c55e">{kw}</b>',
                                        title_hl, flags=re.IGNORECASE
                                    )
                            sub_label = p.get("subreddit", "")
                            sort_label = f" [{p.get('sort','hot')}]" if p.get("sort") != "hot" else ""
                            st.markdown(
                                f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                                f'border-radius:8px;padding:8px 12px;margin-bottom:5px">'
                                f'<div style="font-size:0.82rem;color:#d0d0d0">{title_hl}</div>'
                                f'<div style="font-size:0.72rem;color:#444;margin-top:3px">'
                                f'r/{sub_label}{sort_label} · ▲ {p["score"]:,} · 💬 {p["comments"]} · '
                                f'<a href="{p["url"]}" target="_blank" '
                                f'style="color:#d4a843;text-decoration:none">→ öffnen</a>'
                                f'</div></div>',
                                unsafe_allow_html=True,
                            )

                        # Kommentare on-demand
                        best_post = next((p for p in top_posts if not p["id"].startswith("hn_")), None)
                        if best_post:
                            if st.button(
                                f"💬 Top-Kommentare laden",
                                key=f"comments_{brand}_{i}",
                            ):
                                with st.spinner("Lade Kommentare …"):
                                    comments = _reddit_comments(best_post["id"])
                                if comments:
                                    bull_found = [kw for kw in BULLISH_KEYWORDS
                                                  if any(kw in c.lower() for c in comments)]
                                    bear_found = [kw for kw in BEARISH_KEYWORDS
                                                  if any(kw in c.lower() for c in comments)]
                                    if bull_found or bear_found:
                                        st.markdown(
                                            '<div style="font-size:0.78rem;margin:6px 0">'
                                            + "".join(
                                                f'<span style="background:#0a1a0a;color:#22c55e;'
                                                f'border-radius:4px;padding:1px 6px;margin:2px">{kw}</span>'
                                                for kw in bull_found
                                            )
                                            + "".join(
                                                f'<span style="background:#1a0a0a;color:#ef4444;'
                                                f'border-radius:4px;padding:1px 6px;margin:2px">{kw}</span>'
                                                for kw in bear_found
                                            )
                                            + "</div>",
                                            unsafe_allow_html=True,
                                        )
                                    for c in comments[:8]:
                                        st.markdown(
                                            f'<div style="background:#0e0e0e;border:1px solid #1a1a1a;'
                                            f'border-radius:6px;padding:7px 11px;margin-bottom:4px;'
                                            f'font-size:0.80rem;color:#bbb;line-height:1.5">{c}</div>',
                                            unsafe_allow_html=True,
                                        )

                    # Action Buttons
                    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                    ab1, ab2, ab3 = st.columns(3)
                    if ticker:
                        with ab1:
                            if st.button(f"🔍 {ticker} im Scanner", key=f"scan_{brand}_{i}",
                                         use_container_width=True):
                                st.session_state["scan_ticker_prefill"] = ticker
                                st.switch_page("pages/04_Watchlist_Scanner.py")
                        with ab2:
                            if st.button(f"📊 {ticker} analysieren", key=f"anl_{brand}_{i}",
                                         use_container_width=True):
                                st.session_state["selected_ticker"] = ticker
                                st.switch_page("pages/03_Aktienanalyse.py")
                    with ab3 if ticker else ab1:
                        st.markdown(
                            f'<a href="https://finance.yahoo.com/quote/{ticker or ""}" '
                            f'target="_blank" style="display:block;text-align:center;'
                            f'background:#1a1a1a;border:1px solid #333;border-radius:8px;'
                            f'padding:5px;color:#d4a843;font-size:0.8rem;text-decoration:none">'
                            f'→ Chart &amp; News</a>' if ticker else "",
                            unsafe_allow_html=True,
                        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: MANUELL SUCHEN
# ══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown(
        "<div style='font-size:0.85rem;color:#888;margin-bottom:16px'>"
        "Gib einen Trend, ein Produkt oder eine Marke ein — App sucht Reddit nach "
        "aktuellen Posts und ordnet die passende Aktie zu."
        "</div>",
        unsafe_allow_html=True,
    )

    m_col1, m_col2 = st.columns([3, 1])
    with m_col1:
        manual_query = st.text_input(
            "Produkt / Trend / Marke suchen",
            placeholder="z.B. 'ozempic', 'on running', 'cybertruck', 'GLP-1', 'AI glasses' …",
            help="Freitext-Suche: App sucht Reddit nach Posts mit diesem Begriff",
        )
    with m_col2:
        manual_sort = st.selectbox(
            "Reddit sortieren nach",
            ["relevance", "new", "hot", "top"],
            index=0,
        )

    if manual_query and st.button("🔍 Suchen", type="primary"):
        import requests as _req

        @st.cache_data(ttl=300, show_spinner=False)
        def _reddit_search(query: str, sort: str) -> list[dict]:
            headers = {"User-Agent": "StillhalterApp/2.1"}
            posts = []
            try:
                url = f"https://www.reddit.com/search.json?q={query}&sort={sort}&limit=25&type=link"
                r = _req.get(url, headers=headers, timeout=12)
                if r.status_code == 200:
                    for child in r.json().get("data", {}).get("children", []):
                        p = child.get("data", {})
                        title = p.get("title", "")
                        text  = p.get("selftext", "")[:400]
                        combined = title + " " + text
                        brands = _find_brands(combined)
                        # Auch manuelle Query als Brand-Match prüfen
                        q_lower = query.lower()
                        for b, t in BRAND_TICKER.items():
                            if b in q_lower or q_lower in b:
                                if b not in brands:
                                    brands.append(b)
                        bull = sum(1 for kw in BULLISH_KEYWORDS if kw in combined.lower())
                        bear = sum(1 for kw in BEARISH_KEYWORDS if kw in combined.lower())
                        posts.append({
                            "id": p.get("id", ""),
                            "title": title,
                            "text": text[:200],
                            "score": p.get("score", 0),
                            "comments": p.get("num_comments", 0),
                            "subreddit": p.get("subreddit", ""),
                            "url": "https://reddit.com" + p.get("permalink", ""),
                            "brands": brands,
                            "bull": bull,
                            "bear": bear,
                            "sort": sort,
                        })
            except Exception:
                pass
            return posts

        with st.spinner(f"Suche Reddit nach '{manual_query}' …"):
            m_posts = _reddit_search(manual_query, manual_sort)

        if not m_posts:
            st.warning("Keine Ergebnisse. Versuche einen anderen Begriff oder Sort-Modus.")
        else:
            # Passende Ticker finden
            q_lower = manual_query.lower()
            direct_ticker = None
            for brand, tkr in BRAND_TICKER.items():
                if brand in q_lower or q_lower in brand:
                    direct_ticker = tkr
                    break

            # Metriken
            total_bull = sum(p["bull"] for p in m_posts)
            total_bear = sum(p["bear"] for p in m_posts)
            net_sent   = (total_bull - total_bear) / max(total_bull + total_bear, 1) * 100

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Posts gefunden", len(m_posts))
            mc2.metric("Bullish Signale", total_bull)
            mc3.metric("Bearish Signale", total_bear)
            mc4.metric("Net Sentiment",   f"{net_sent:+.0f}%")

            # Ticker-Infos
            if direct_ticker:
                si = _stock_info(direct_ticker)
                if si:
                    r90c = "#22c55e" if si["r90"] >= 0 else "#ef4444"
                    st.markdown(
                        f'<div style="background:#0a0a0a;border:1px solid {si["color"]}44;'
                        f'border-left:3px solid {si["color"]};border-radius:10px;'
                        f'padding:12px 16px;margin:10px 0">'
                        f'<span style="background:#d4a843;color:#000;font-weight:700;'
                        f'font-size:0.85rem;padding:2px 10px;border-radius:12px">{direct_ticker}</span>'
                        f' <span style="font-size:0.85rem;color:#f0f0f0;margin-left:8px">'
                        f'${si["price"]:.2f}</span>'
                        f' <span style="color:{r90c};font-size:0.85rem">'
                        f'{si["r90"]:+.1f}% 90T</span>'
                        f'<div style="font-size:0.78rem;color:{si["color"]};margin-top:6px;font-weight:600">'
                        f'📊 Einpreisung: {si["label"]}</div>'
                        f'<div style="font-size:0.75rem;color:#666">{si["hint"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Posts anzeigen
            st.markdown(f"**📰 {len(m_posts)} Reddit-Posts zu '{manual_query}':**")
            for p in m_posts[:15]:
                title_hl = p["title"]
                for kw in BULLISH_KEYWORDS:
                    if kw in title_hl.lower():
                        title_hl = re.sub(
                            re.escape(kw),
                            f'<b style="color:#22c55e">{kw}</b>',
                            title_hl, flags=re.IGNORECASE
                        )
                for kw in BEARISH_KEYWORDS:
                    if kw in title_hl.lower():
                        title_hl = re.sub(
                            re.escape(kw),
                            f'<b style="color:#ef4444">{kw}</b>',
                            title_hl, flags=re.IGNORECASE
                        )
                bull_dot = "🟢" if p["bull"] > 0 else ("🔴" if p["bear"] > 0 else "⚪")
                st.markdown(
                    f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                    f'border-radius:8px;padding:9px 13px;margin-bottom:5px">'
                    f'<div style="font-size:0.83rem;color:#d0d0d0">{bull_dot} {title_hl}</div>'
                    f'<div style="font-size:0.72rem;color:#444;margin-top:3px">'
                    f'r/{p["subreddit"]} · ▲ {p["score"]:,} · 💬 {p["comments"]} · '
                    f'<a href="{p["url"]}" target="_blank" '
                    f'style="color:#d4a843;text-decoration:none">→ öffnen</a>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: STOCKTWITS TRENDING
# ══════════════════════════════════════════════════════════════════════════════
with tab_stocktwits:
    st.markdown(
        "<div style='font-size:0.85rem;color:#888;margin-bottom:16px'>"
        "StockTwits zeigt welche Aktien die Community gerade am meisten diskutiert — "
        "direktes Momentum-Signal ohne Umweg über Produkte."
        "</div>",
        unsafe_allow_html=True,
    )

    sw1, sw2 = st.columns([2, 6])
    with sw1:
        sw_btn = st.button("📊 StockTwits Trending laden", type="primary",
                           use_container_width=True)
        sw_rescan = st.button("🔄 Neu laden", use_container_width=True,
                              help="Cache leeren und frische Daten holen",
                              disabled="stocktwits_data" not in st.session_state)
    with sw2:
        st.markdown(
            "<div style='padding-top:8px;font-size:0.78rem;color:#555'>"
            "Zeigt die von der Trading-Community meistdiskutierten Aktien in Echtzeit. "
            "Kostenlose API · Kein Key benötigt · 10 Min. gecacht"
            "</div>",
            unsafe_allow_html=True,
        )

    if sw_rescan:
        _stocktwits_trending.clear()
        if "stocktwits_data" in st.session_state:
            del st.session_state["stocktwits_data"]
        st.rerun()

    if sw_btn:
        with st.spinner("Lade StockTwits Trending Tickers …"):
            st_tickers = _stocktwits_trending()
        if st_tickers:
            st.session_state["stocktwits_data"] = st_tickers
            st.session_state["stocktwits_time"] = datetime.now().strftime("%H:%M")
            st.rerun()
        else:
            st.warning(
                "⚠️ **StockTwits API hat keine Daten zurückgegeben.** "
                "Mögliche Ursachen: API-Rate-Limit, temporäre Wartung oder Netzwerkfehler. "
                "Bitte in 1–2 Minuten erneut versuchen.",
                icon="📊",
            )

    st_tickers = st.session_state.get("stocktwits_data", [])
    st_time    = st.session_state.get("stocktwits_time", "–")

    if not st_tickers:
        st.info(
            "👆 **'StockTwits Trending laden'** klicken — zeigt die meistdiskutierten "
            "Aktien der Trading-Community in Echtzeit.",
            icon="📊",
        )
    else:
        st.markdown(
            f"<div style='font-size:0.75rem;color:#444;margin-bottom:12px'>"
            f"✅ {len(st_tickers)} Trending Tickers · Stand {st_time} Uhr"
            f"</div>",
            unsafe_allow_html=True,
        )

        st_cols = st.columns(3)
        for i, sym in enumerate(st_tickers):
            ticker = sym.get("ticker", "")
            title  = sym.get("title", "")
            wl     = sym.get("watchlist", 0)
            if not ticker:
                continue

            sinfo = _stock_info(ticker)
            r90_str  = f"{sinfo['r90']:+.1f}%" if sinfo else "–"
            r90_col  = ("#22c55e" if sinfo.get("r90", 0) >= 0 else "#ef4444") if sinfo else "#888"
            price_str = f"${sinfo['price']:.2f}" if sinfo else "–"

            with st_cols[i % 3]:
                st.markdown(
                    f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                    f'border-radius:10px;padding:10px 14px;margin-bottom:8px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<span style="background:#d4a843;color:#000;font-weight:700;'
                    f'font-size:0.9rem;padding:2px 10px;border-radius:10px">{ticker}</span>'
                    f'<span style="font-size:0.75rem;color:#444">👁 {wl:,}</span>'
                    f'</div>'
                    f'<div style="font-size:0.78rem;color:#888;margin-top:5px">{title}</div>'
                    f'<div style="font-size:0.85rem;color:#f0f0f0;margin-top:4px">'
                    f'{price_str} <span style="color:{r90_col}">{r90_str}</span>'
                    f' <span style="font-size:0.65rem;color:#444">90T</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Sortierbare Tabelle
        if st_tickers:
            rows = []
            for sym in st_tickers:
                tkr = sym.get("ticker", "")
                si  = _stock_info(tkr) if tkr else {}
                rows.append({
                    "Ticker": tkr,
                    "Unternehmen": sym.get("title", ""),
                    "Watchlist": sym.get("watchlist", 0),
                    "Kurs": round(si.get("price", 0), 2) if si else None,
                    "30T %": round(si.get("r30", 0), 1) if si else None,
                    "90T %": round(si.get("r90", 0), 1) if si else None,
                    "Einpreisung": si.get("label", "–") if si else "–",
                })
            df_st = pd.DataFrame(rows)
            st.dataframe(
                df_st, use_container_width=True, hide_index=True, height=480,
                column_config={
                    "Watchlist": st.column_config.NumberColumn("👁 Watchlist", format="%d"),
                    "Kurs":      st.column_config.NumberColumn("Kurs", format="$%.2f"),
                    "30T %":     st.column_config.NumberColumn("30T %", format="%.1f%%"),
                    "90T %":     st.column_config.NumberColumn("90T %", format="%.1f%%"),
                },
            )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="font-size:0.72rem;color:#333;text-align:center">'
    'Quellen: Reddit JSON-API · Google Trends (pytrends) · StockTwits API · '
    'Product Hunt RSS · Hacker News Firebase API · Live-Kursdaten'
    '</div>',
    unsafe_allow_html=True,
)
