"""Value and provenance axes for duplicates; never resolves an occurrence."""
from collections import Counter
import json
from .analysis import id_sort, occurrence
from .restoration import digest


def audit_duplicates(data):
    rows=[]
    for name,ds in sorted(data.items()):
        for sid,entries in sorted(ds.entries.items(),key=lambda item:id_sort(item[0])):
            if len(entries)<2: continue
            values={e.value for e in entries}
            invalid=sid in ds.invalid_ids or any(e.ambiguous for e in entries)
            classification='different_values' if len(values)>1 else 'other_invalid' if invalid else 'same_value_safe'
            locations=[json.dumps(occurrence(e),sort_keys=True) for e in entries]
            paths={e.path for e in entries}
            repeated=len(set(locations))<len(locations)
            provenance=('repeated_same_location' if len(set(locations))==1 else 'mixed_repeated_location' if repeated
                        else 'within_file_distinct_locations' if len(paths)==1 else 'cross_file')
            rows.append(dict(dataset=name,string_id=sid,classification=classification,
                provenance_class=provenance,entry_count=len(entries),distinct_value_count=len(values),
                safe_meaning='literal values agree only; occurrence/load order remains unresolved' if classification=='same_value_safe' else None,
                occurrences=[dict(**occurrence(e),value_sha256=digest(e.value),value_excerpt=e.value[:200],
                                  excerpted=len(e.value)>200) for e in entries]))
    causes=Counter((r['dataset'],tuple(sorted({o['path'] for o in r['occurrences']})),r['classification']) for r in rows)
    return dict(total=len(rows),value_counts={c:sum(r['classification']==c for r in rows)
                for c in ('same_value_safe','different_values','other_invalid')},
                provenance_counts={c:sum(r['provenance_class']==c for r in rows) for c in
                    ('within_file_distinct_locations','cross_file','repeated_same_location','mixed_repeated_location')},
                source_groups=[dict(dataset=n,paths=list(paths),classification=c,count=count) for (n,paths,c),count in sorted(causes.items())],
                dataset_counts={n:dict(sorted(Counter(r['classification'] for r in rows if r['dataset']==n).items())) for n in sorted(data)},rows=rows)
