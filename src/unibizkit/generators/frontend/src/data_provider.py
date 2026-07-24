import json
from ..context import Context
from .resources.helpers import build_m2m_config


def generate(ctx: Context) -> str:
    m2m_config = build_m2m_config(ctx.concepts, ctx.concept_map)
    m2m_config_json = json.dumps(m2m_config, indent=2)

    return f"""import {{ supabaseDataProvider }} from 'ra-supabase';
import {{ supabaseClient }} from './supabaseClient';

const supabaseUrl = window.location.origin + import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_KEY;

const baseDataProvider = supabaseDataProvider({{
  instanceUrl: supabaseUrl,
  apiKey: supabaseKey,
  supabaseClient: supabaseClient
}});

const m2mConfig = {m2m_config_json};

export const dataProvider = {{
  ...baseDataProvider,

  getOne: async (resource, params) => {{
    const result = await baseDataProvider.getOne(resource, params);
    const config = m2mConfig[resource];

    if (config) {{
      await Promise.all(Object.keys(config).map(async (field) => {{
         const {{ resource: joinResource, linkField, targetField }} = config[field];
         const {{ data }} = await supabaseClient
             .from(joinResource)
             .select(`"${{targetField}}"`)
             .eq(`"${{linkField}}"`, result.data.id);

         if (data) {{
             result.data[field] = data.map(item => item[targetField]);
         }}
      }}));
    }}
    return result;
  }},

  create: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};

     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field]) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}

     const result = await baseDataProvider.create(resource, params);

     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const ids = m2mIds[field];
            if (ids && ids.length > 0) {{
                const rows = ids.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                await supabaseClient.from(joinResource).insert(rows);
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }},

  update: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};

     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field] !== undefined) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}

     const result = await baseDataProvider.update(resource, params);

     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const newIds = m2mIds[field];

            // Diff the join rows instead of delete+reinsert. Besides avoiding
            // unnecessary writes, this keeps relation history limited to links
            // the user actually added or removed.
            const {{ data: existingRows, error: existingError }} = await supabaseClient
                .from(joinResource)
                .select(`"${{targetField}}"`)
                .eq(`"${{linkField}}"`, id);
            if (existingError) throw existingError;
            const existingIds = (existingRows || []).map(row => row[targetField]);
            const wantedIds = newIds || [];
            const removedIds = existingIds.filter(existingId => !wantedIds.some(wantedId => String(wantedId) === String(existingId)));
            const addedIds = wantedIds.filter(wantedId => !existingIds.some(existingId => String(existingId) === String(wantedId)));
            if (removedIds.length > 0) {{
                const {{ error }} = await supabaseClient.from(joinResource)
                    .delete()
                    .eq(`"${{linkField}}"`, id)
                    .in(`"${{targetField}}"`, removedIds);
                if (error) throw error;
            }}
            if (addedIds.length > 0) {{
                const rows = addedIds.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                const {{ error }} = await supabaseClient.from(joinResource).insert(rows);
                if (error) throw error;
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }}
}};
"""
