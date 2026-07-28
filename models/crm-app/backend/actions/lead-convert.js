// Convert Lead — the signature CRM action.
//
// A qualified lead becomes three records: the company (account), the person (contact) and
// the deal (opportunity). The three inserts run with `supabase`, the caller's client, so
// row-level security still decides whether this user may create them. Only the conversion
// audit trail on the lead itself is written with `serviceClient`, because those fields are
// read-only for sales reps and marketers (rules_level_3) precisely so nobody can rewrite
// what a lead became.
//
// Re-running it on an already converted lead is a no-op that reports what it became, so a
// double click cannot create a second account.

const DAYS_TO_FIRST_CLOSE_DATE = 30;

export async function run({ ids, supabase, serviceClient }) {
  const results = [];

  for (const leadId of ids) {
    try {
      results.push(await convertOne(leadId, supabase, serviceClient));
    } catch (error) {
      return { status: "ko", message: `Lead ${leadId}: ${error.message}` };
    }
  }

  return { status: "ok", message: results.join(" ") };
}

async function convertOne(leadId, supabase, serviceClient) {
  const lead = await fetchOne(
    supabase.from("lead").select("*").eq("id", leadId).single(),
    "read the lead",
  );

  if (lead.status === "converted") {
    return `${lead.company} was already converted.`;
  }
  if (lead.status !== "qualified") {
    throw new Error("only a qualified lead can be converted");
  }

  // An account with the same registered name is the same company: reuse it instead of
  // failing on the unique name, which is what a rep expects when several leads arrive
  // from one company.
  const { data: existing, error: lookupError } = await supabase
    .from("account")
    .select("id")
    .eq("name", lead.company)
    .limit(1);
  if (lookupError) throw new Error(`could not look for the account: ${lookupError.message}`);

  let accountId = existing?.[0]?.id ?? null;
  let accountCreated = false;
  if (accountId === null) {
    const account = await fetchOne(
      supabase
        .from("account")
        .insert({
          name: lead.company,
          type: "prospect",
          industry: lead.industry,
          rating: lead.rating,
          website: lead.website,
          phone: lead.phone,
          employees: lead.num_employees,
          annual_revenue: lead.annual_revenue,
          billing_city: lead.city,
          billing_country: lead.country,
          description: lead.description,
        })
        .select("id")
        .single(),
      "create the account",
    );
    accountId = account.id;
    accountCreated = true;

    // Who owns an account is a management decision, so account.owner is read-only for
    // reps and marketers (rules_level_3). Converting a lead is the one moment where the
    // ownership is not a decision but a consequence — the rep who worked the lead keeps
    // the company — so the action writes it with the privileged client.
    const { error: ownerError } = await serviceClient
      .from("account")
      .update({ owner: lead.owner })
      .eq("id", accountId);
    if (ownerError) throw new Error(`could not set the account owner: ${ownerError.message}`);
  }

  const contact = await fetchOne(
    supabase
      .from("contact")
      .insert({
        account: accountId,
        salutation: lead.salutation,
        first_name: lead.first_name ?? "—",
        last_name: lead.last_name,
        title: lead.title,
        email: lead.email,
        phone: lead.phone,
        mobile: lead.mobile,
        owner: lead.owner,
        lead_source: lead.lead_source,
      })
      .select("id")
      .single(),
    "create the contact",
  );

  const closeDate = new Date();
  closeDate.setDate(closeDate.getDate() + DAYS_TO_FIRST_CLOSE_DATE);
  const opportunity = await fetchOne(
    supabase
      .from("opportunity")
      .insert({
        account: accountId,
        name: `${lead.company} — first deal`,
        type: "new_business",
        close_date: closeDate.toISOString().slice(0, 10),
        owner: lead.owner,
        primary_contact: contact.id,
        campaign: lead.campaign,
        lead_source: lead.lead_source,
        next_step: "Agree on the discovery call",
      })
      .select("id")
      .single(),
    "create the opportunity",
  );

  // The calls and emails already logged against the lead are the history of the
  // relationship: point them at the records that now hold it, keeping the lead reference
  // so the origin of the conversation stays visible.
  const { error: activityError } = await supabase
    .from("activity")
    .update({ account: accountId, contact: contact.id, opportunity: opportunity.id })
    .eq("lead", leadId);
  if (activityError) throw new Error(`could not move the activities: ${activityError.message}`);

  const { error: leadError } = await serviceClient
    .from("lead")
    .update({
      status: "converted",
      converted_date: new Date().toISOString().slice(0, 10),
      converted_account: accountId,
      converted_contact: contact.id,
      converted_opportunity: opportunity.id,
    })
    .eq("id", leadId);
  if (leadError) throw new Error(`could not close the lead: ${leadError.message}`);

  const accountPart = accountCreated ? "new account" : "existing account";
  return `${lead.company}: contact and opportunity created on the ${accountPart}.`;
}

async function fetchOne(query, what) {
  const { data, error } = await query;
  if (error) throw new Error(`could not ${what}: ${error.message}`);
  return data;
}
