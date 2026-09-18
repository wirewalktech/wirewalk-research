#!/usr/bin/env python3
"""Health check for every Wirewalk site. Re-runnable; exits non-zero on any failure.

    python3 tools/check-sites.py            # all sites
    python3 tools/check-sites.py www ai     # named sites only

Checks, per site:
  1. DNS resolves to GitHub Pages
  2. GitHub Pages is enabled, built, has the right CNAME, and enforces HTTPS
  3. http:// redirects to https://
  4. Every page reachable from the homepage returns 200
  5. No stale baseurl path appears in any link or asset reference
  6. Every link resolves; every #fragment matches a real id on its target page
  7. The contact form carries action/method/name and posts to its configured backend

Two mistakes this script exists to prevent, both of which shipped to production:

  * Crawling wirewalktech.github.io instead of the live custom domain. GitHub
    301s the old URL to the custom domain, which masked the fact that every
    /wirewalk-site/... link 404d for real visitors. Roots here are always the
    domains users land on.
  * Treating a rendered "Thank you" as proof of delivery. The old contact form
    had no action/method/name and its JS printed a success message without
    sending anything. Check 7 asserts the markup, not the message.

Requires: python3 (stdlib only) and, for the Pages checks, `gh` authenticated.
"""
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# "phone" is the number that site is expected to publish. The AI practice
# deliberately lists a different one from the engineering sites, so this is
# per-site rather than a single global expectation.
SITES = {
    "research": {"domain": "research.wirewalk.com", "repo": "wirewalk-research",
                 "form": True, "phone": "516-269-1517"},
}

# Repo-name paths that must never appear in a rendered link (the baseurl bug).
STALE = ["/wirewalk-site/", "/AI-Extension/", "/print-wirewalk/", "/studio-wirewalk/", "/wirewalk-research/"]
GH_PAGES_IPS = {"185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"}

UA = {"User-Agent": "Mozilla/5.0 (wirewalk-site-check)"}
CTX = ssl.create_default_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, newurl, headers, fp)


_FOLLOW = urllib.request.build_opener()
_NOFOLLOW = urllib.request.build_opener(_NoRedirect)

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
failures = []


def ok(msg):
    print(f"    {GREEN}PASS{OFF}  {msg}")


def bad(site, msg):
    print(f"    {RED}FAIL{OFF}  {msg}")
    failures.append(f"{site}: {msg}")


def note(msg):
    print(f"    {YELLOW}··{OFF}    {msg}")


def fetch(url, follow=True):
    """-> (status, body, location). status 0 means the request never completed."""
    opener = _FOLLOW if follow else _NOFOLLOW
    try:
        with opener.open(urllib.request.Request(url, headers=UA), timeout=25) as r:
            ctype = r.headers.get("Content-Type", "")
            body = r.read().decode("utf-8", "ignore") if ("html" in ctype or "xml" in ctype) else ""
            return r.status, body, None
    except urllib.error.HTTPError as e:
        loc = None
        if e.headers:
            loc = e.headers.get("Location")
        if not loc and isinstance(e.msg, str) and e.msg.startswith("http"):
            loc = e.msg
        return e.code, "", loc
    except Exception as e:
        return 0, "", f"{type(e).__name__}: {e}"[:80]


# Homebrew's bin is not on the default PATH in a non-login zsh here, so a
# bare `gh` returns 127 and the Pages checks silently report "not enabled".
# A checker that raises a false alarm gets ignored, which is worse than one
# that does not run at all.
_ENV = dict(os.environ)
_ENV["PATH"] = os.pathsep.join([
    "/opt/homebrew/bin", os.path.expanduser("~/bin"), _ENV.get("PATH", "")])


def sh(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=45, env=_ENV)
        return p.stdout.strip()
    except Exception:
        return ""


def have_gh():
    return bool(sh("command -v gh"))


RESOURCE_HINT = re.compile(
    r'<link\b[^>]*\brel="(?:preconnect|dns-prefetch|preload|prefetch|prerender|modulepreload)"[^>]*>',
    re.I)


def navigable(body):
    """Drop resource-hint <link> tags before harvesting hrefs.

    A rel="preconnect" href is an ORIGIN to warm a connection to, not a
    document: https://fonts.gstatic.com correctly answers 404 to a GET, and
    treating it as a broken link is a false positive. Same for dns-prefetch
    and the preload family.
    """
    return RESOURCE_HINT.sub("", body)


def is_real_link(href):
    """Skip hrefs that are actually fragments of JavaScript string concatenation.

    An earlier version of this check reported 12 phantom broken anchors by
    matching href="#'+h.id+'" inside a <script> block.
    """
    return href.strip() not in ("", "#") and not any(c in href for c in "'+{")


def crawl(root):
    """Fetch the homepage and every internal HTML page it links to."""
    pages, todo, seen = {}, [root], set()
    while todo:
        url = todo.pop(0)
        if url in seen:
            continue
        seen.add(url)
        status, body, _ = fetch(url)
        pages[url] = (status, body)
        if status != 200 or "<html" not in body.lower():
            continue
        for href in re.findall(r'href="([^"]+)"', navigable(body)):
            if not is_real_link(href) or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            full = urllib.parse.urljoin(url, href).split("?")[0].split("#")[0]
            if (full.startswith(root) and full not in seen
                    and not re.search(r"\.(png|jpe?g|svg|ico|webp|pptx|docx|pdf|xml|css|js|mp4|mp3|webm)$",
                                      full, re.I)):
                todo.append(full)
    return pages


def check_site(key, cfg):
    domain, repo = cfg["domain"], cfg["repo"]
    root = f"https://{domain}/"
    print(f"\n{'=' * 70}\n  {key}  —  {domain}  ({repo})\n{'=' * 70}")

    # 1. DNS
    resolved = set(sh(f"dig +short {domain} @8.8.8.8").split())
    if GH_PAGES_IPS & resolved:
        ok(f"DNS -> GitHub Pages ({len(GH_PAGES_IPS & resolved)}/4 edge IPs)")
    else:
        bad(key, f"DNS does not resolve to GitHub Pages (got: {resolved or 'nothing'})")
        return

    # 2. Pages configuration
    if not have_gh():
        note("gh not available - skipping Pages configuration checks")
        raw = ""
    else:
        raw = sh(f"gh api repos/wirewalktech/{repo}/pages 2>/dev/null")
    if not raw and have_gh():
        bad(key, "GitHub Pages is not enabled on the repo")
    elif not raw:
        pass
    else:
        try:
            p = json.loads(raw)
        except json.JSONDecodeError:
            p = {}
        if p.get("status") == "built":
            ok("Pages build status: built")
        else:
            bad(key, f"Pages build status: {p.get('status')}")
        if p.get("cname") == domain:
            ok(f"CNAME configured: {domain}")
        else:
            bad(key, f"CNAME is {p.get('cname')!r}, expected {domain!r}")
        cert = (p.get("https_certificate") or {}).get("state")
        if p.get("https_enforced"):
            ok(f"HTTPS enforced (cert {cert})")
        else:
            bad(key, f"HTTPS NOT enforced (cert state: {cert}) — "
                     f"fix: gh api -X PUT /repos/wirewalktech/{repo}/pages -F https_enforced=true")

    # 3. http -> https
    st, _, loc = fetch(f"http://{domain}/", follow=False)
    if st in (301, 302, 307, 308) and loc and loc.startswith("https://"):
        ok(f"http:// redirects to https:// ({st})")
    elif st == 200:
        bad(key, "http:// serves 200 instead of redirecting to https://")
    else:
        note(f"http:// returned {st} {loc or ''}")

    # 4. pages reachable
    pages = crawl(root)
    broken_pages = [(u, s) for u, (s, _) in pages.items() if s != 200]
    if broken_pages:
        for u, s in broken_pages:
            bad(key, f"page {s}: {u}")
    else:
        ok(f"all {len(pages)} pages return 200")

    # 5. stale baseurl paths
    stale = [(u, h) for u, (_, b) in pages.items()
             for h in re.findall(r'(?:href|src)="([^"]+)"', b)
             if any(p in h for p in STALE)]
    if stale:
        for u, h in stale[:6]:
            bad(key, f"stale baseurl link {h}  (on {u})")
        if len(stale) > 6:
            bad(key, f"...and {len(stale) - 6} more stale links")
    else:
        ok("no stale baseurl paths in any link or asset")

    # 6. links and fragments
    #
    # A THIRD-PARTY HOST REFUSING A SCRIPT IS NOT A BROKEN LINK. The credits
    # page carries an attribution link for every licensed photograph, and
    # stocksnap.io, rawpixel.com and openverse.org all answer 403 to anything
    # that is not a real browser -- they block on TLS fingerprint, so a
    # browser User-Agent does not help either. Reporting ~120 of those as
    # failures buries the one that matters and trains everyone to ignore the
    # checker, which is the exact failure this file was written to prevent.
    #
    # So: 403/405/429 from an EXTERNAL host is reported as unverifiable, with
    # a count. 404, 410 and 5xx stay failures wherever they come from -- a
    # licence link that 404s leaves a reader unable to check what they may do
    # with the file, and one of those did ship. Anything on this site's own
    # domain is still held to 200, refusal included.
    BLOCKED = {401, 403, 405, 429}
    checked, broken, refused, n_links = {}, [], [], 0
    for page_url, (status, body) in sorted(pages.items()):
        if status != 200:
            continue
        ids = set(re.findall(r'id="([^"]+)"', body))
        for href in sorted(set(re.findall(r'href="([^"]+)"', navigable(body)))):
            if not is_real_link(href) or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            n_links += 1
            if href.startswith("#"):
                if href[1:] not in ids:
                    broken.append((page_url, href, "no matching id on page"))
                continue
            target = urllib.parse.urljoin(page_url, href)
            base, _, frag = target.partition("#")
            if base not in checked:
                checked[base] = fetch(base)
                time.sleep(0.03)
            st, tbody, _ = checked[base]
            external = not base.startswith(root)
            if st == 200:
                if frag and tbody and f'id="{frag}"' not in tbody:
                    broken.append((page_url, href, "fragment missing on target page"))
            elif external and st in BLOCKED:
                refused.append((urllib.parse.urlsplit(base).netloc, st))
            else:
                broken.append((page_url, href, f"HTTP {st}"))
    if broken:
        for page_url, href, why in broken:
            bad(key, f"{href} — {why}  (on {page_url})")
    else:
        ok(f"{n_links} links checked, {len(checked)} distinct targets, 0 broken")
    if refused:
        hosts = {}
        for host, st in refused:
            hosts.setdefault(f"{host} ({st})", 0)
            hosts[f"{host} ({st})"] += 1
        note("could not verify from a script (host refuses non-browser requests): "
             + ", ".join(f"{h} x{n}" for h, n in sorted(hosts.items())))

    # 7. every post in _posts actually rendered
    #
    # A post Jekyll declined to build -- a future date is the usual cause --
    # produces NO broken link, because nothing links to a page that was never
    # generated. Every other check passes and the article is simply absent.
    # This is the only check that can see that.
    pdir = cfg.get("posts_dir")
    if pdir and os.path.isdir(pdir):
        import datetime
        missing, future = [], []
        today = datetime.date.today()
        names = [f for f in os.listdir(pdir) if f.endswith((".md", ".markdown", ".html"))]
        for fn in sorted(names):
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+?)\.(md|markdown|html)$", fn)
            if not m:
                continue
            y, mo, d, slug = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            expected = urllib.parse.urljoin(root, cfg["post_url"].format(slug=slug))
            st, _, _ = fetch(expected)
            if st != 200:
                (future if datetime.date(y, mo, d) > today else missing).append((fn, st, expected))
        if future:
            for fn, st, u in future:
                bad(key, f"post dated in the FUTURE so Jekyll skipped it: {fn} -> {st}")
        if missing:
            for fn, st, u in missing:
                bad(key, f"post did not render: {fn} -> {st} at {u}")
        if not missing and not future:
            ok(f"all {len(names)} posts rendered and reachable")

    # 8. contact form
    if cfg.get("form"):
        home = pages.get(urllib.parse.urljoin(root, "/contact/"), (0, ""))[1]
        forms = re.findall(r"<form\b.*?</form>", home, re.S)
        allowed = ("formsubmit.co", "wirewalk-portal.wirewalk-upload.workers.dev/api/enquiry")
        target = next((f for f in forms if any(a in f for a in allowed)), None)
        if not target:
            bad(key, "no contact form with an approved backend found on the contact page")
        else:
            for label, cond in [
                ("form action -> approved backend", any(a in target for a in allowed)),
                ('method="POST"', re.search(r'method="post"', target, re.I) is not None),
                ('input name="name"', 'name="name"' in target),
                ('input name="email"', 'name="email"' in target),
                ("honeypot present", "_honey" in target),
                ("_next -> /thanks/", "/thanks/" in target),
            ]:
                (ok if cond else lambda m: bad(key, m))(label)
            st, _, _ = fetch(urllib.parse.urljoin(root, "/thanks/"))
            (ok if st == 200 else lambda m: bad(key, m))(f"/thanks/ returns {st}")
        phone = cfg.get("phone")
        if phone:
            tel = "tel:+1" + phone.replace("-", "")
            if phone in home and tel in home:
                ok(f"phone {phone} present as a tel: link")
            else:
                bad(key, f"phone {phone} missing or not a tel: link")


def main():
    wanted = sys.argv[1:] or list(SITES)
    unknown = [w for w in wanted if w not in SITES]
    if unknown:
        print(f"unknown site(s): {', '.join(unknown)}\nknown: {', '.join(SITES)}")
        return 2
    for key in wanted:
        check_site(key, SITES[key])

    print(f"\n{'=' * 70}")
    if failures:
        print(f"  {RED}{len(failures)} FAILURE(S){OFF}")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"  {GREEN}ALL CHECKS PASSED{OFF}")
    print(f"{DIM}  Note: this verifies form wiring and response pages, not end-to-end email delivery.{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
