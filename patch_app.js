const fs = require('fs');
let code = fs.readFileSync('frontend/app.js', 'utf8');

const target1 = `    effectiveRfd3Input,
    rfd3Mode: normalizedRfd3Mode,
    inferredContig,
  } = resolveRfd3Defaults({`;

const insert1 = `    effectiveRfd3Input,
    rfd3Mode: normalizedRfd3Mode,
    inferredContig,
    inferredUnindex,
    inferredSelectFixedAtoms,
  } = resolveRfd3Defaults({`;

code = code.replace(target1, insert1);

const target2 = `  if (inferredContig) {
    answers.rfd3_contig = inferredContig;
  }`;

const insert2 = `  if (inferredContig) {
    answers.rfd3_contig = inferredContig;
  }
  if (inferredUnindex) {
    answers.rfd3_unindex = inferredUnindex;
  }
  if (inferredSelectFixedAtoms) {
    answers.rfd3_select_fixed_atoms = inferredSelectFixedAtoms;
  }`;

code = code.replace(target2, insert2);
fs.writeFileSync('frontend/app.js', code);
console.log("Patched app.js");
