import re

with open("pipeline-mcp/src/pipeline_mcp/pipeline.py", "r") as f:
    code = f.read()

# _rfd3_simple_inputs is called from _rfd3_requested_design_chains AND during rfd3 stage itself.
# BUT wait, the pdb text given to _rfd3_simple_inputs in _rfd3_requested_design_chains is request.rfd3_input_pdb
# which has NOT been stripped of negative residues yet!
# The stripping happens in `run()`, but `_rfd3_requested_design_chains` is called BEFORE stripping!
# This means `residues_by_chain` gets the raw PDB with negative residues!
# So `res_list[0].resseq` might be -8, making contig A-7-221!

t = """            if pdb_text.strip():
                by_chain = residues_by_chain(pdb_text)
                if by_chain:
                    first_chain = sorted(by_chain.keys())[0]
                    res_list = by_chain[first_chain]
                    if len(res_list) > 1:
                        unindex_val = f"{first_chain}{res_list[0].resseq}"
                        fixed_val = {unindex_val: "ALL"}
                        if contig_val is None:
                            contig_val = f"{first_chain}{res_list[1].resseq}-{res_list[-1].resseq}\""""

insert = """            if pdb_text.strip():
                from .bio.pdb import _has_nonpositive_resseq, _prepare_pdb_text_for_design_context
                # Strip negative residues temporarily for inference if needed, because RFD3 fails on negative contigs
                if _has_nonpositive_resseq(pdb_text):
                    pdb_text = _prepare_pdb_text_for_design_context(pdb_text, strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
                
                by_chain = residues_by_chain(pdb_text)
                if by_chain:
                    first_chain = sorted(by_chain.keys())[0]
                    res_list = by_chain[first_chain]
                    if len(res_list) > 1:
                        unindex_val = f"{first_chain}{res_list[0].resseq}"
                        fixed_val = {unindex_val: "ALL"}
                        if contig_val is None:
                            contig_val = f"{first_chain}{res_list[1].resseq}-{res_list[-1].resseq}\""""

code = code.replace(t, insert)

with open("pipeline-mcp/src/pipeline_mcp/pipeline.py", "w") as f:
    f.write(code)

with open("frontend/lib/pipeline.js", "r") as f:
    js_code = f.read()

js_target = """  const normalized = Object.entries(ranges).reduce((acc, [chainId, entry]) => {
    if (entry.minPos === null || entry.maxPos === null) return acc;
    acc[chainId] = { min: entry.minPos, max: entry.maxPos };
    return acc;
  }, {});"""

# In JS, inferredRfd3ContigRanges already ignores resSeq <= 0:
# if (resSeq > 0) {
#   entry.minPos = entry.minPos === null ? resSeq : Math.min(entry.minPos, resSeq);
# }
# So JS is safe.
