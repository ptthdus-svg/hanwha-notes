// 커뮤니티 새 글·댓글 → 알림을 켠 사람들에게 웹 푸시 보내기
// DB 트리거(supabase/03-push.sql)가 새 글과 구독 목록을 같이 보내줘요. 이 함수는 DB 키가 필요 없어요.
// 환경 변수(Secrets): VAPID_PUBLIC, VAPID_PRIVATE, HOOK_SECRET
import webpush from "npm:web-push@3.6.7";

const SITE = "https://ptthdus-svg.github.io/hanwha-notes/";
const SB_URL = Deno.env.get("SUPABASE_URL") ?? "";
const PUBLISHABLE = "sb_publishable_ZkX-cJ2WpXarHCZzBhvCmw_bYdlRK3L";

webpush.setVapidDetails(SITE, Deno.env.get("VAPID_PUBLIC")!, Deno.env.get("VAPID_PRIVATE")!);

type Sub = { endpoint: string; p256dh: string; auth: string };

Deno.serve(async (req) => {
  if (req.headers.get("x-hook-secret") !== Deno.env.get("HOOK_SECRET")) {
    return new Response("forbidden", { status: 403 });
  }
  const { post, news, subs } = (await req.json()) as {
    post?: { id: number; parent_id: number | null; category: string; nickname: string; body: string };
    news?: { count: number; first: string };
    subs: Sub[];
  };
  const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  let payload: string;
  if (news) {
    // 한화 소식: 한 번 수집에 알림 1개
    payload = JSON.stringify({
      title: `한화 소식 ${news.count}건`,
      body: short(news.first.replace(/\s+/g, " "), 100) + (news.count > 1 ? ` 외 ${news.count - 1}건` : ""),
      url: "./#news",
      tag: "news",
    });
  } else if (post) {
    const isComment = post.parent_id != null;
    payload = JSON.stringify({
      title: isComment ? `새 댓글 · ${post.nickname}` : `새 글 [${post.category}] · ${post.nickname}`,
      body: short(post.body.replace(/\s+/g, " "), 120),
      url: "./#board",
      tag: "board-" + (post.parent_id ?? post.id),
    });
  } else {
    return new Response("bad request", { status: 400 });
  }

  let sent = 0;
  const gone: string[] = [];
  await Promise.all((subs ?? []).map(async (s) => {
    try {
      await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } }, payload, { TTL: 60 * 60 * 24 });
      sent++;
    } catch (e) {
      const code = (e as { statusCode?: number }).statusCode;
      if (code === 404 || code === 410) gone.push(s.endpoint); // 알림을 끈 기기
    }
  }));
  // 만료된 구독 정리
  await Promise.all(gone.map((endpoint) =>
    fetch(`${SB_URL}/rest/v1/rpc/push_unsubscribe`, {
      method: "POST",
      headers: { apikey: PUBLISHABLE, "Content-Type": "application/json" },
      body: JSON.stringify({ p_endpoint: endpoint }),
    }).catch(() => {})
  ));
  return Response.json({ sent, removed: gone.length });
});
