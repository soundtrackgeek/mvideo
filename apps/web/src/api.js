export class APIError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}
export async function request(path, { body, ...options } = {}) {
  const token = sessionStorage.getItem("mvideo-session");
  const response = await fetch(path, {
    ...options,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    redirect: "error",
  });
  const data = await response.json();
  if (!response.ok)
    throw new APIError(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the entered values.",
      response.status,
    );
  return data;
}
