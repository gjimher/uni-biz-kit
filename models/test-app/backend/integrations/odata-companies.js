export async function fetchPage({ cursor, checkpoint, pageSize }) {
  const basePort = Number(Deno.env.get("UBK_DEV_BASE_PORT"));
  if (!Number.isInteger(basePort)) throw new Error("UBK_DEV_BASE_PORT must be an integer");
  const baseUrl = `http://host.docker.internal:${basePort + 11}`;
  let url;
  if (cursor?.nextLink) {
    url = cursor.nextLink.replace(/^https?:\/\/[^/]+/, baseUrl);
  } else {
    const params = new URLSearchParams({ "$top": String(pageSize) });
    if (checkpoint?.modifiedOn) params.set("$filter", `modifiedOn gt ${checkpoint.modifiedOn}`);
    url = `${baseUrl}/odata/v4/Accounts?${params}`;
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`OData source returned HTTP ${response.status}`);
  const body = await response.json();
  const latest = body.value.reduce(
    (value, record) => record.modifiedOn > value ? record.modifiedOn : value,
    checkpoint?.modifiedOn ?? "",
  );
  const removed = body.value.filter((record) => record["@removed"]);
  return {
    items: body.value.filter((record) => !record["@removed"]),
    removedExternalIds: removed.map((record) => record.accountId),
    nextCursor: body["@odata.nextLink"] ? { nextLink: body["@odata.nextLink"] } : null,
    complete: !body["@odata.nextLink"],
    checkpoint: { modifiedOn: latest },
  };
}
