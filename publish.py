#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Habliko Mastodon publisher
--------------------------
Version SOCIAL del automatismo (posts cortos, no articulos):
  - 8 idiomas (es, en, fr, de, nl, it, pt, lb) desde UNA cuenta
  - frase/tip corta generada con Groq + enlace al blog del idioma + hashtags
  - imagen 1x1 de frase (R2) adjunta como media
  - una tanda por ejecucion, recorriendo los 8 idiomas (con pacing de Groq)
  - progress.json lleva el puntero de tema por idioma
  - CUALQUIER fallo por idioma NO tumba el run; al final marca rojo si hubo fallos

Secrets necesarios (GitHub Actions -> Settings -> Secrets -> Actions):
  GROQ_API_KEY
  MASTODON_TOKEN   (token de acceso de tu app de Mastodon)

Antes de usar: pon tu instancia en MASTODON_INSTANCE (ej. https://mastodon.social).
"""

import os
import sys
import json
import time
import urllib.parse
import urllib.request
import urllib.error

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# PROVEEDORES DE IA (Cerebras principal + Groq respaldo; ambos gpt-oss-120b).
#   Cerebras: ~1.000.000 tokens/dia gratis | Groq: ~200.000 tokens/dia gratis
# ----------------------------------------------------------------------------
PROVIDERS = [
    {
        "name": "cerebras",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "key_env": "CEREBRAS_API_KEY",
        "model": "gpt-oss-120b",
        "max_tokens": 2000,
        "reasoning_effort": "low",
    },
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        "max_tokens": 2000,
        "reasoning_effort": "low",
    },
]
USER_AGENT = "habliko-publisher/1.0"

# >>> PON AQUI TU INSTANCIA DE MASTODON (sin barra final) <<<
MASTODON_INSTANCE = "https://mastodon.social"
MASTODON_STATUS = MASTODON_INSTANCE + "/api/v1/statuses"
MASTODON_MEDIA = MASTODON_INSTANCE + "/api/v2/media"

# El post enlaza al blog del idioma (es.habliko.com, en.habliko.com, ...)
BLOG_URL_TMPL = "https://{lang}.habliko.com"

# Imagen 1x1 de frase servida por el media worker de R2
ADD_IMAGE = True
MEDIA_RANDOM = "https://media.habliko.com/random/habliko/img/1x1/phrase/{lang}"

# Pacing de Groq (free tier ~8000 tokens/min)
SLEEP_BETWEEN_LANGS = 75
GROQ_RETRIES = 2

LANGUAGES = ["es", "en", "fr", "de", "nl", "it", "pt", "lb"]

LANG_NAMES = {
    "es": "Spanish (espanol de Espana)",
    "en": "English",
    "fr": "French (francais)",
    "de": "German (Deutsch)",
    "nl": "Dutch (Nederlands)",
    "it": "Italian (italiano)",
    "pt": "Portuguese (portugues de Portugal)",
    "lb": "Luxembourgish (Letzebuergesch)",
}

PROGRESS_FILE = "progress.json"

TOPICS = [
    {"num": 1,  "theme": "How to build a daily language-learning habit that sticks"},
    {"num": 2,  "theme": "The best way to memorize vocabulary long-term with spaced repetition"},
    {"num": 3,  "theme": "Understanding the CEFR levels: from A1 to C2 explained simply"},
    {"num": 4,  "theme": "How many words you really need to hold a conversation"},
    {"num": 5,  "theme": "Why speaking from day one accelerates your learning"},
    {"num": 6,  "theme": "Common mistakes beginners make and how to avoid them"},
    {"num": 7,  "theme": "How to stay motivated when learning a language feels slow"},
    {"num": 8,  "theme": "Learning a language as an adult: why it's never too late"},
    {"num": 9,  "theme": "The difference between active and passive vocabulary"},
    {"num": 10, "theme": "How to improve your accent and pronunciation"},
    {"num": 11, "theme": "Shadowing: the technique that improves fluency fast"},
    {"num": 12, "theme": "How to learn a language in just 15 minutes a day"},
    {"num": 13, "theme": "The role of comprehensible input in language acquisition"},
    {"num": 14, "theme": "How to start thinking in your target language"},
    {"num": 15, "theme": "Best strategies to overcome the fear of speaking"},
    {"num": 16, "theme": "How mini-games make learning a language fun and effective"},
    {"num": 17, "theme": "Setting realistic language goals with the CEFR framework"},
    {"num": 18, "theme": "Why immersion works and how to create it at home"},
    {"num": 19, "theme": "How to learn two languages at the same time"},
    {"num": 20, "theme": "The psychology of motivation in language learning"},
    {"num": 21, "theme": "How to remember grammar rules without boring drills"},
    {"num": 22, "theme": "Flashcards vs. context: which helps you learn faster"},
    {"num": 23, "theme": "How to expand your vocabulary every single day"},
    {"num": 24, "theme": "The most useful phrases to learn first in any language"},
    {"num": 25, "theme": "How to practice listening comprehension effectively"},
    {"num": 26, "theme": "Why making mistakes is essential to learning a language"},
    {"num": 27, "theme": "How to keep a learning streak going without burning out"},
    {"num": 28, "theme": "Learning idioms and expressions the natural way"},
    {"num": 29, "theme": "How to prepare for a language exam (A2, B1, B2)"},
    {"num": 30, "theme": "The benefits of learning a language for your brain"},
    {"num": 31, "theme": "How children learn languages and what adults can copy"},
    {"num": 32, "theme": "How to learn a language before a trip abroad"},
    {"num": 33, "theme": "Reading in a foreign language: where to start"},
    {"num": 34, "theme": "How to use an AI tutor to practice conversation"},
    {"num": 35, "theme": "The secret to consistent daily practice"},
    {"num": 36, "theme": "How to measure your progress in a new language"},
    {"num": 37, "theme": "Spanish for beginners: first steps and essentials"},
    {"num": 38, "theme": "English pronunciation tips for non-native speakers"},
    {"num": 39, "theme": "French grammar basics every beginner should know"},
    {"num": 40, "theme": "German cases explained simply for beginners"},
    {"num": 41, "theme": "Common false friends between languages and how to spot them"},
    {"num": 42, "theme": "How to learn Luxembourgish and why it's worth it"},
    {"num": 43, "theme": "Italian for travelers: essential words and phrases"},
    {"num": 44, "theme": "Portuguese and Spanish: key differences to know"},
    {"num": 45, "theme": "Dutch pronunciation: the sounds that trip learners up"},
    {"num": 46, "theme": "How to build sentences confidently in a new language"},
    {"num": 47, "theme": "The best times of day to study a language"},
    {"num": 48, "theme": "How to review vocabulary so you never forget it"},
    {"num": 49, "theme": "Learning through songs, films and podcasts"},
    {"num": 50, "theme": "How to talk about yourself in your target language"},
    {"num": 51, "theme": "Numbers, dates and time: mastering the basics"},
    {"num": 52, "theme": "How to order food and drinks in another language"},
    {"num": 53, "theme": "Greetings and small talk in any language"},
    {"num": 54, "theme": "How to ask for directions abroad without panic"},
    {"num": 55, "theme": "Everyday routines vocabulary for beginners"},
    {"num": 56, "theme": "How to describe people and places fluently"},
    {"num": 57, "theme": "Past, present and future: verb tenses made easy"},
    {"num": 58, "theme": "How to sound more polite in a foreign language"},
    {"num": 59, "theme": "Business language essentials for professionals"},
    {"num": 60, "theme": "How to write your first email in a new language"},
    {"num": 61, "theme": "The most common verbs you should learn first"},
    {"num": 62, "theme": "How to understand fast native speech"},
    {"num": 63, "theme": "Building confidence through small daily wins"},
    {"num": 64, "theme": "How to create a personalized study plan"},
    {"num": 65, "theme": "Why variety in practice keeps learning fresh"},
    {"num": 66, "theme": "How to learn vocabulary by topic (food, travel, work)"},
    {"num": 67, "theme": "The power of repetition without boredom"},
    {"num": 68, "theme": "How gamification boosts language retention"},
    {"num": 69, "theme": "How to practice speaking when you're alone"},
    {"num": 70, "theme": "Overcoming plateaus in language learning"},
    {"num": 71, "theme": "How bilingualism benefits your career"},
    {"num": 72, "theme": "Learning a language with your kids at home"},
    {"num": 73, "theme": "How to use spaced repetition the right way"},
    {"num": 74, "theme": "The role of grammar: how much do you really need"},
    {"num": 75, "theme": "How to make foreign-language friends online"},
    {"num": 76, "theme": "Cultural context: why it matters when learning a language"},
    {"num": 77, "theme": "How to prepare for real conversations"},
    {"num": 78, "theme": "Micro-learning: fitting practice into a busy life"},
    {"num": 79, "theme": "How to stop translating in your head"},
    {"num": 80, "theme": "The most effective free ways to practice every day"},
    {"num": 81, "theme": "How to keep learning after reaching B1"},
    {"num": 82, "theme": "Reaching C1 and C2: what advanced learners do differently"},
    {"num": 83, "theme": "How to teach yourself a language from scratch"},
    {"num": 84, "theme": "Study routines that actually work long-term"},
    {"num": 85, "theme": "How to enjoy the process, not just the goal"},
    {"num": 86, "theme": "Why tracking your streak keeps you accountable"},
    {"num": 87, "theme": "How a friendly tutor helps you learn a little every day"},
    {"num": 88, "theme": "From zero to conversation: a realistic timeline"},
    {"num": 89, "theme": "How to choose which language to learn next"},
    {"num": 90, "theme": "Turning language learning into a lifelong habit"},
]


# ----------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------


def _post_json(url, payload, headers, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _read_http_error(e):
    try:
        return e.read().decode("utf-8", "replace")
    except Exception:
        return str(e)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)
    else:
        p = {}
    p.setdefault("topic_pointer", {})
    for lang in LANGUAGES:
        p["topic_pointer"].setdefault(lang, 0)
    return p


def save_progress(p):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def _parse_json_lenient(content):
    if not content:
        raise ValueError("Groq devolvio una respuesta VACIA")
    try:
        return json.loads(content)
    except Exception:
        pass
    c = content.strip()
    if c.startswith("```"):
        c = c.strip("`")
        if c.lstrip().lower().startswith("json"):
            c = c.lstrip()[4:]
        c = c.strip()
        try:
            return json.loads(c)
        except Exception:
            pass
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start:end + 1])
        except Exception:
            pass
    print("---- RESPUESTA CRUDA DE GROQ (no era JSON) ----")
    print(content[:800])
    raise ValueError("No se pudo interpretar la respuesta de Groq como JSON")


# ----------------------------------------------------------------------------
# GROQ (post corto)
# ----------------------------------------------------------------------------


def _provider_request(provider, system, user):
    payload = {
        "model": provider["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.85,
        "max_tokens": provider.get("max_tokens", 2000),
        "response_format": {"type": "json_object"},
    }
    if provider.get("reasoning_effort"):
        payload["reasoning_effort"] = provider["reasoning_effort"]
    headers = {"Authorization": "Bearer " + os.environ[provider["key_env"]]}
    resp = _post_json(provider["url"], payload, headers)
    return (resp["choices"][0]["message"]["content"] or "").strip()


def _multi_generate(system, user):
    active = [p for p in PROVIDERS if os.environ.get(p["key_env"])]
    if not active:
        raise RuntimeError("Ningun proveedor tiene API key (CEREBRAS/GROQ)")
    last = None
    for p in active:
        try:
            content = _provider_request(p, system, user)
            if p is not active[0]:
                print("   (respaldo: %s)" % p["name"])
            return content
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("   %s dio 429; pruebo el siguiente..." % p["name"])
                last = e
                continue
            last = e
            break
        except Exception as e:
            last = e
            break
    raise last or RuntimeError("Fallo la generacion en todos los proveedores")


def groq_short(lang, theme):
    lang_name = LANG_NAMES[lang]
    system = (
        "You write short, punchy social media posts for Habliko, a friendly "
        "language-learning app whose mascot is Foxi, a fox tutor. Warm, useful, "
        "never spammy."
    )
    user = (
        "Write ONE short social post ENTIRELY in {lang_name} about this topic:\n"
        "{theme}\n\n"
        "Rules:\n"
        "- MAX 300 characters. One concrete tip or an inspiring phrase for learners.\n"
        "- No links and no hashtags inside the text (added separately).\n"
        "- Natural, human tone. You may use 1-2 emojis.\n\n"
        "Return ONLY valid JSON, no fences:\n"
        '{{"text": "...", "hashtags": ["#tag1", "#tag2", "#tag3"]}}\n'
        "- hashtags: 2-3 relevant tags (language learning). Short."
    ).format(lang_name=lang_name, theme=theme)

    content = _multi_generate(system, user)
    art = _parse_json_lenient(content)
    if not art.get("text"):
        raise ValueError("El proveedor no devolvio 'text'")
    if not isinstance(art.get("hashtags"), list):
        art["hashtags"] = []
    return art


def groq_short_retry(lang, theme):
    attempt = 0
    while True:
        try:
            return groq_short(lang, theme)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < GROQ_RETRIES:
                wait = 30 * (attempt + 1)
                print("   429 rate limit; espero %ss y reintento..." % wait)
                time.sleep(wait)
                attempt += 1
                continue
            raise


# ----------------------------------------------------------------------------
# IMAGEN (descarga de R2)
# ----------------------------------------------------------------------------


def fetch_image_bytes(lang):
    """Descarga una 1x1 de frase del idioma. Devuelve (bytes, content_type) o None."""
    if not ADD_IMAGE:
        return None
    url = MEDIA_RANDOM.format(lang=lang)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "image/png")
            return data, ctype
    except Exception as e:
        print("   AVISO: sin imagen (%r)" % e)
        return None


# ----------------------------------------------------------------------------
# MASTODON
# ----------------------------------------------------------------------------


def mastodon_upload_media(img_bytes, content_type, alt):
    """Sube la imagen a /api/v2/media (multipart) y devuelve el media id."""
    boundary = "----habliko%d" % int(time.time() * 1000)
    ext = "png" if "png" in content_type else "jpg"
    parts = []
    # campo description (alt text)
    parts.append(("--%s\r\n" % boundary).encode())
    parts.append(b'Content-Disposition: form-data; name="description"\r\n\r\n')
    parts.append(alt.encode("utf-8") + b"\r\n")
    # campo file
    parts.append(("--%s\r\n" % boundary).encode())
    parts.append(
        ('Content-Disposition: form-data; name="file"; filename="phrase.%s"\r\n'
         % ext).encode()
    )
    parts.append(("Content-Type: %s\r\n\r\n" % content_type).encode())
    parts.append(img_bytes + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode())
    body = b"".join(parts)

    headers = {
        "Authorization": "Bearer " + os.environ["MASTODON_TOKEN"],
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
        "User-Agent": USER_AGENT,
    }
    req = urllib.request.Request(MASTODON_MEDIA, data=body, headers=headers,
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out.get("id")


def mastodon_post(text, lang, media_id):
    fields = [
        ("status", text),
        ("language", lang),
        ("visibility", "public"),
    ]
    if media_id:
        fields.append(("media_ids[]", media_id))
    data = urllib.parse.urlencode(fields).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + os.environ["MASTODON_TOKEN"],
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    req = urllib.request.Request(MASTODON_STATUS, data=data, headers=headers,
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out.get("url") or out.get("uri") or "(sin url)"


def compose(art, lang):
    """Monta el texto final: frase + enlace al blog + hashtags, <= 500 chars."""
    blog = BLOG_URL_TMPL.format(lang=lang)
    tags = " ".join(art.get("hashtags", [])[:3])
    text = art["text"].strip()
    # dejar hueco para enlace + hashtags
    tail = "\n\n" + blog + ("\n" + tags if tags else "")
    room = 490 - len(tail)
    if len(text) > room:
        text = text[:room - 1].rstrip() + "\u2026"
    return text + tail


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------


def publish_one(lang, progress):
    topic_idx = progress["topic_pointer"][lang] % len(TOPICS)
    topic = TOPICS[topic_idx]
    print("-" * 60)
    print("Idioma %s (%s) | Tema #%d: %s"
          % (lang, LANG_NAMES[lang], topic["num"], topic["theme"]))

    art = groq_short(lang, topic["theme"])

    media_id = None
    got = fetch_image_bytes(lang)
    if got:
        try:
            media_id = mastodon_upload_media(got[0], got[1], art["text"][:200])
        except Exception as e:
            print("   AVISO: fallo subiendo imagen (%r). Publico sin foto." % e)

    text = compose(art, lang)
    url = mastodon_post(text, lang, media_id)
    print("   OK publicado: %s" % url)

    progress["topic_pointer"][lang] = topic_idx + 1
    return url


def main():
    if not os.environ.get("MASTODON_TOKEN"):
        print("ERROR: falta secret MASTODON_TOKEN")
        sys.exit(1)
    active = [p["name"] for p in PROVIDERS if os.environ.get(p["key_env"])]
    if not active:
        print("ERROR: falta al menos una API key de IA "
              "(CEREBRAS_API_KEY y/o GROQ_API_KEY)")
        sys.exit(1)
    print("Proveedores IA (en orden): %s" % ", ".join(active))
    if "TU_INSTANCIA" in MASTODON_INSTANCE or not MASTODON_INSTANCE.startswith("http"):
        print("ERROR: configura MASTODON_INSTANCE con tu instancia real.")
        sys.exit(1)

    progress = load_progress()
    print("== Habliko Mastodon publisher (los 8 idiomas) ==")
    print("Instancia: %s" % MASTODON_INSTANCE)

    ok_list, fail_list = [], []
    for i, lang in enumerate(LANGUAGES):
        try:
            publish_one(lang, progress)
            ok_list.append(lang)
        except urllib.error.HTTPError as e:
            print("   ERROR HTTP %s en '%s': %s"
                  % (e.code, lang, _read_http_error(e)))
            fail_list.append(lang)
        except Exception as e:
            print("   ERROR en '%s': %r" % (lang, e))
            fail_list.append(lang)
        save_progress(progress)
        if i < len(LANGUAGES) - 1:
            print("   ... espero %ss (limite Groq) ..." % SLEEP_BETWEEN_LANGS)
            time.sleep(SLEEP_BETWEEN_LANGS)

    print("=" * 60)
    print("Resumen: %d OK (%s) | %d fallos (%s)"
          % (len(ok_list), ", ".join(ok_list) or "-",
             len(fail_list), ", ".join(fail_list) or "-"))
    if fail_list:
        sys.exit(1)


if __name__ == "__main__":
    main()
