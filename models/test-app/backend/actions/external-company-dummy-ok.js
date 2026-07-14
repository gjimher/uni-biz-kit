export async function run({ ids, supabase }) {
  const { data, error } = await supabase
    .from("external_company")
    .select("name")
    .in("id", ids);

  if (error) return { status: "ko", message: `Could not read companies: ${error.message}` };
  const names = data.map((company) => company.name).join(", ");
  return { status: "ok", message: `Dummy OK received: ${names}` };
}
