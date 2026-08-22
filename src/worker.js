const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});

function authorized(request, env) {
  const expected = env.ADMIN_TOKEN;
  return expected && request.headers.get("authorization") === `Bearer ${expected}`;
}

async function listGames(env) {
  const { results } = await env.DB.prepare(
    "SELECT id, url, title, source, base_price, discounted_price, discount_pct, checked_at, added_at FROM games ORDER BY added_at DESC"
  ).all();
  return results;
}

async function api(request, env, url) {
  if (url.pathname === "/api/games" && request.method === "GET") {
    return json({ games: await listGames(env) });
  }

  if (!authorized(request, env)) return json({ error: "Unauthorized" }, 401);

  if (url.pathname === "/api/games" && request.method === "POST") {
    const body = await request.json().catch(() => null);
    const gameUrl = typeof body?.url === "string" ? body.url.trim() : "";
    const title = typeof body?.title === "string" ? body.title.trim() : "";
    const source = typeof body?.source === "string" ? body.source.trim().toLowerCase() : "";
    const domains = {
      playstation: /^https:\/\/store\.playstation\.com\//i,
      flipkart: /^https:\/\/(?:www\.)?flipkart\.com\//i,
      amazon: /^https:\/\/(?:www\.)?amazon\.(?:in|com)\//i,
    };
    if (!domains[source] || !domains[source].test(gameUrl)) {
      return json({ error: "Choose a marketplace and enter a valid product URL." }, 400);
    }
    try {
      await env.DB.prepare("INSERT INTO games (url, title, source) VALUES (?, ?, ?)")
        .bind(gameUrl, title, source).run();
    } catch (error) {
      if (String(error).toLowerCase().includes("unique")) {
        return json({ error: "That game is already on the wishlist." }, 409);
      }
      throw error;
    }
    return json({ games: await listGames(env) }, 201);
  }

  const match = url.pathname.match(/^\/api\/games\/(\d+)$/);
  if (match && request.method === "PATCH") {
    const body = await request.json().catch(() => null);
    const title = typeof body?.title === "string" ? body.title.trim() : "";
    const basePrice = Number(body?.base_price);
    const discountedPrice = Number(body?.discounted_price);
    const discountPct = Number(body?.discount_pct);
    if (!title || !Number.isFinite(basePrice) || !Number.isFinite(discountedPrice) || !Number.isFinite(discountPct)) {
      return json({ error: "Invalid price data." }, 400);
    }
    await env.DB.prepare(
      "UPDATE games SET title = ?, base_price = ?, discounted_price = ?, discount_pct = ?, checked_at = CURRENT_TIMESTAMP WHERE id = ?"
    ).bind(title, basePrice, discountedPrice, discountPct, match[1]).run();
    return json({ games: await listGames(env) });
  }

  if (match && request.method === "DELETE") {
    await env.DB.prepare("DELETE FROM games WHERE id = ?").bind(match[1]).run();
    return json({ games: await listGames(env) });
  }

  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      try {
        return await api(request, env, url);
      } catch (error) {
        return json({ error: "Database request failed." }, 500);
      }
    }
    return env.ASSETS.fetch(request);
  },
};