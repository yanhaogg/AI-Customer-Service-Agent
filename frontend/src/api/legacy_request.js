// LEGACY: 早期请求封装，当前使用 lib/shop.js 与 lib/catalog.js。
const BASE_URL = "http://localhost:8000";

export async function request(url, options = {}) {
  const token = localStorage.getItem("token");

  return fetch(BASE_URL + url, {
    ...options,

    headers: {
      "Content-Type": "application/json",

      Authorization: `Bearer ${token}`,
    },
  });
}
