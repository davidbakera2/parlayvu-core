<!--
  Ingested by ParlayVU client_file_ingester.
  Source: Reports/Structural Incompatibility of Negative-Air Cleaning in Flexible HVAC Duct Systems.pdf
  Source last modified: 2026-05-26 13:54 UTC
  Ingested at: 2026-05-26 18:58 UTC
  Extracted text size: 16656 characters
  Re-ingest with: python -m app.services.client_file_ingester <client_id> [--force]
-->

# Structural Incompatibility of Negative-Air Cleaning in Flexible HVAC Duct Systems

### Executive Summary

This is a peer-reviewed journal article (CIRI Journal, Spring 2026, Vol. 7, Issue 1) by David Hart arguing that negative-air duct cleaning is structurally incompatible with flexible HVAC duct systems and should not be used where flex duct is present or suspected. The core finding: flex duct is engineered for positive pressure and has low peel strength at its adhesive seams — negative-air equipment routinely exceeds the duct's rated tolerance (½"–1" WC), causing delamination, liner perforation, collapse, and hidden internal failures that visual inspection cannot detect. Independent lab testing by Element Materials Technology confirmed these failure modes across 12" and 19" diameter samples under negative pressure with agitation. The paper also argues that the theoretical safeguard protocol (duct-type ID, pressure tolerance verification, real-time monitoring) is operationally impractical in real field conditions due to concealed runs, mixed materials, and undocumented retrofits. Positive pressure cleaning is presented as the mechanically compatible alternative — it operates within the duct's design parameters and requires none of the safeguards negative-air demands. The paper calls for updated industry cleaning standards to reflect these vulnerabilities.

---

### Key Findings

- Flexible HVAC ducting is structurally incompatible with negative-air cleaning because it is engineered for positive pressure and has significantly lower peel strength than shear strength at its adhesive seams.
- Negative-air equipment — especially truck-mounted machines — routinely exceeds the rated negative-pressure tolerance of flex duct (½"–1" WC), causing delamination and liner perforation.
- Independent lab testing (Element Materials Technology, Feb. 2026) confirmed visible holes and adhesive seam failures in 12" and 19" diameter flex duct samples subjected to negative pressure combined with mechanical agitation.
- Internal delamination failures are frequently undetectable by visual inspection because external insulation masks internal damage and failures occur within the duct wall itself.
- Seam compromise during high-humidity conditions (e.g., crawlspaces, attics in summer) can draw in moisture-laden unconditioned air, promoting condensation and mold colonization inside the duct system.
- The required three-step safeguard protocol (pre-cleaning inspection, pressure tolerance verification, real-time pressure monitoring) is deemed operationally impractical due to inaccessible duct runs, mixed materials, undocumented retrofits, and insulation-wrapped sections.
- If flex duct cannot be identified or ruled out, the system must be treated as though flex duct is present and the lowest tolerance (½" WC) must be assumed.
- Positive pressure cleaning is presented as a mechanically compatible alternative that eliminates inward-directed forces, requires no duct-type identification, and operates within the duct's inherent structural limits.
- The paper concludes that negative-air duct cleaning is not an appropriate or reasonable method for any modern HVAC system containing or potentially containing flexible ducting.
- The primary failure mode — peel-strength deterioration at the structural seam — is often undetectable through standard visual inspection, meaning compromised systems may remain in service and expose occupants to contaminants.

---

### Notable Data Points

- **½"–1" WC:** Rated negative-pressure tolerance range for flexible HVAC ducting per Air Diffusion Council (2018) — the threshold negative-air equipment routinely exceeds.
- **½" WC:** Default assumed tolerance when duct manufacturer/model cannot be identified (most conservative assumption required by the protocol).
- **4,000 CFM:** Maximum airflow rating of the portable negative-air machine used in lab testing.
- **8 lab samples total:** Eight flexible HVAC duct samples tested (12" and 19" diameters) across control, negative-pressure-only, and negative-pressure-with-agitation conditions.
- **12" and 19" diameters:** Duct sizes tested; increased diameter did not mitigate susceptibility to damage.
- **6-tentacle air whip:** Agitation tool used in testing, powered by a Champion HGR7-3H air compressor, advanced at ~5 seconds per linear foot.
- **Element Materials Technology W.O. No. PUS17001081, dated 11 February 2026:** Lab testing work order reference.
- **Miles, Hart & Luckey (2023):** Prior foundational study — "Effects of Negative Air Duct Cleaning on Flex Ducting," published in Restoration & Remediation Magazine — cited repeatedly as the basis for this paper's findings.
- **ASTM D1876-08(2020):** Standard test method for peel resistance of adhesives, cited to support the peel-vs.-shear strength distinction in flex duct seams.
- **Air Diffusion Council (2018):** *Flexible Duct Performance & Installation Standards* (5th ed.) — primary engineering standard cited for pressure tolerances.
- **John Miles:** President and chief science officer at Superstratum; credited as developer of the seam-seal adhesives used in flex duct; quoted on field observations of mold growth following negative-air cleaning.
- **CIRI Journal Spring 2026, Volume 7, Issue 1, pages 6–9:** Publication details for this article.

---

### Open Questions / Followups

- The paper acknowledges the three-step safeguard protocol but declares it "entirely impractical" — no alternative compliance pathway or interim standard is proposed beyond switching to positive pressure; it is unclear whether any industry body has formally adopted or is considering the recommended standard updates.
- No acceptance or rejection criteria were defined in the Element Materials Technology test protocol — the implications for how results should be interpreted in a regulatory or standards context are not addressed.
- The paper does not specify what positive pressure cleaning equipment or methods were tested or validated; the compatibility claim is based on design-principle reasoning, not parallel lab testing.
- The scope of "modern HVAC systems" is not defined — the paper does not address hybrid systems, older all-metal systems, or systems where flex duct percentage is minimal.
- No cost, liability, or insurance implications of switching from negative-air to positive pressure methods are discussed.
- The paper does not address whether existing industry standards (e.g., NADCA) currently permit or restrict negative-air cleaning in flex duct systems, or what the path to standard revision would look like.
- RamAir International's specific role, use case, or relationship to this research is not stated in the document — context for why this was shared with the ParlayVU team is not present in the source.

---

## Full Extracted Text

--- page 1 ---
Extracted Article: "Structural Incompatibility of Negative-Air Cleaning in Flexible 
HVAC Duct Systems" by David Hart (Full, clean text from pages 6–9 of the CIRI Journal 
Spring 2026, Volume 7, Issue 1. This is the complete standalone article, free of surrounding 
journal material, advertisements, or unrelated content. It can be copied directly into a word 
processor, Markdown-to-PDF converter, or LaTeX tool to produce a professional separate 
PDF document.) 
Structural Incompatibility of Negative-Air Cleaning in Flexible HVAC Duct Systems By 
David Hart 
Abstract Negative-air duct cleaning is a common practice in HVAC remediation, but it 
poses notable risks when used with flexible duct systems. (In HVAC remediation, 
"negative-air" refers to mechanically inducing negative pressure inside a duct system using 
vacuum equipment to draw airflow toward a collection device.) Building on previous 
studies that highlighted adhesive weaknesses and delamination issues in flex ducts, 
including research published in Restoration & Remediation Magazine (Miles, Hart & Luckey, 
2023), this paper reviews engineering standards and material-science principles (Air 
Diffusion Council, 2018) to show that negative-air cleaning would require a three-step 
safeguard protocol: inspection, pressure-tolerance verification, and real-time monitoring, 
to avoid exceeding the mechanical limits of flexible ducting. 
The analysis identifies peel-strength deterioration at the structural seam as the primary 
failure mode, often undetectable through standard visual inspection (ASTM International, 
2020). To contextualize these findings, the Positive Pressure method is evaluated for its 
mechanical compatibility with flex duct construction, as it operates within the higher 
positive-pressure tolerances for which these systems are designed. The results support 
updating cleaning standards to reflect the inherent vulnerabilities of flexible HVAC 
ductwork and the practical limitations of applying negative-pressure methods in systems 
where flex duct may be present. 
Background Flexible HVAC ducting is commonly utilized in residential and commercial 
environments due to its cost-effectiveness and routing flexibility. Nonetheless, its 
structural characteristics restrict its capacity to withstand negative pressure, generally 
between ½" and 1" water column (WC) (Air Diffusion Council, 2018). Negative-air duct-
cleaning methods frequently impose vacuum pressures that surpass manufacturer 
specifications for flexible ducts, as previously detailed in Effects of Negative Air Duct 
Cleaning on Flex Ducting (Miles et al., 2023). This disparity between equipment capability 
and duct design has contributed to widespread, often undetected structural failures.

--- page 2 ---
Negative-air machines, especially those mounted on trucks, are capable of producing 
negative pressures which exceed the tolerances of flex-duct construction. Under such 
conditions, the inner liner may be pulled inward with sufficient force to separate it from the 
outer jacket, resulting in delamination, a failure mode substantiated in Effects of Negative 
Air Duct Cleaning on Flex Ducting (Miles et al., 2023). 
Field observations and post-cleaning analyses reveal that internal delamination occurs 
more frequently than previously acknowledged. This form of failure permits particulate 
infiltration and moisture ingress, fostering environments favorable to microbial 
proliferation. HVAC ducts located in crawlspaces tend to be closer to outdoor ambient 
temperatures and often experience elevated relative humidity, intensifying moisture-
related damages. 
Expanding upon the findings presented in Effects of Negative Air Duct Cleaning on Flex 
Ducting (Miles et al., 2023), this paper combines material science perspectives with field 
data to assess the incompatibility between negative-air cleaning techniques and flexible 
duct systems. The objective is to encourage safer cleaning practices and advocate for 
revised standards that address the structural limitations inherent in flexible HVAC ducting. 
Materials and methods Independent laboratory testing conducted by Element Materials 
Technology provides controlled, empirical validation of the failure mechanisms associated 
with negative-air duct cleaning in flexible HVAC duct systems. In this evaluation, eight 
flexible HVAC duct samples of 12-inch and 19-inch diameters were subjected to varying 
conditions, including control (no applied pressure), negative pressure only, and negative 
pressure combined with mechanical agitation, replicating conditions commonly 
encountered during duct-cleaning operations. 
A section of 8-inch diameter flexible HVAC ducting was connected to a portable negative 
air machine with a maximum airflow rating of 4,000 CFM. To simulate typical field cleaning 
conditions, the duct was also subjected to internal mechanical agitation using a standard 
six-tentacle air whip powered by a Champion HGR7-3H air compressor. The whip was 
advanced through the sample length at a controlled rate of approximately five seconds per 
linear foot. 
Results The testing matrix included both control samples and samples exposed to 
negative pressure with and without agitation. Visual examination and photographic 
documentation were used to assess structural integrity, with particular attention to visible 
holes and seam adhesive failures. Control samples at both diameters exhibited no visible 
damage, confirming baseline material integrity prior to testing. In contrast, samples

--- page 3 ---
exposed to negative pressure, specifically those subjected to agitation, demonstrated a 
consistent pattern of structural compromise. 
Among the 12-inch diameter ducting tested, samples exposed to negative pressure 
combined with agitation exhibited visible holes and adhesive seam peeling. One sample 
exposed to negative pressure alone also demonstrated both failure modes. Similar results 
were observed in the 19-inch diameter ducting, where the sample subjected to negative 
pressure and agitation exhibited visible holes, indicating that increased diameter did not 
mitigate susceptibility to negative pressure induced damage. 
Figure 1 – Inner liner of flexible duct, control sample (12" diameter). Photo courtesy of 
Element Materials Technology. Figure 2 – Failure Mode: Delamination (adhesive strength 
exceeded). Photo courtesy of Element Materials Technology. Figure 3 – Failure Mode: Hole 
(membrane tensile properties exceeded). Photo courtesy of Element Materials Technology. 
Table 1 – Summary of Laboratory Observed Damage to Flexible HVAC Ducting Under 
Negative Pressure Conditions 
Sample ID Duct 
Diameter Test Condition Visible 
Holes 
Visible 
Adhesive 
Peel 
Observed Failure 
Mode 
Control 12 in. No applied 
pressure No No No observable 
damage 
Negative 
Only 12 in. Negative 
pressure only No No No visible damage 
Negative + 
Agitation 1 12 in. 
Negative 
pressure with 
agitation 
Yes Yes Liner perforation and 
seam delamination 
Negative + 
Agitation 2 12 in. 
Negative 
pressure with 
agitation 
Yes Yes Liner perforation and 
adhesive peel 
A – Control 12 in. No applied 
pressure No No No observable 
damage 
B – Negative 
Pressure 12 in. Negative 
pressure only Yes Yes Adhesive seam failure 
and liner damage

--- page 4 ---
Sample ID Duct 
Diameter Test Condition Visible 
Holes 
Visible 
Adhesive 
Peel 
Observed Failure 
Mode 
Control 19 in. No applied 
pressure No No No observable 
damage 
Negative + 
Agitation 19 in. 
Negative 
pressure with 
agitation 
Yes No Liner perforation 
Note. Visible damage was documented through visual examination and photographic 
evidence following exposure to test conditions representative of negative-air duct cleaning 
practices. No acceptance or rejection criteria were defined in the test protocol. Data 
summarized from independent laboratory testing conducted by Element Materials 
Technology (W.O. No. PUS17001081, 11 February 2026). 
Key takeaways from prior research 
• Flexible HVAC ducting is engineered with high shear strength for positive pressure 
environments and lacks the peel strength needed to withstand even mild negative 
pressures beyond those present in return air ducts (ASTM International, 2020). 
• Negative-air duct cleaning equipment routinely exceeds safe pressure tolerances. 
• Adhesive seam seal degradation can result in contamination and moisture ingress 
following negative-air duct cleaning. Common contaminants include pollens, insect 
parts, rodent dropping dust, mold-fungi, fiberglass insulation particulate, etc. 
• Structural failures often occur internally and remain undetected through visual 
inspection. 
Discussion Adhesive failure and peel strength limitations The structural seam of flex 
ducting relies on adhesives that exhibit significantly lower peel strength compared to shear 
strength (ASTM International, 2020). This is intentional, as forced air systems are 
engineered for positive, not negative, pressures. Negative pressure applies a peeling force 
to the seam, stressing the adhesive bond at its weakest. When vacuum pressures exceed 
manufacturer tolerances, the peel force can surpass the adhesive's capacity, resulting in 
delamination, a failure mode consistent with the findings of (Miles et al. 2023). 
Collapse and deformation under excessive negative pressure Flexible ducting is 
designed for positive pressure airflow, where internal pressure pushes outward against the

--- page 5 ---
duct wall. Negative air cleaning moves air in the opposite direction of the system's 
intended airflow, pulling the liner inward. When negative pressure exceeds the ducting's 
rated tolerance, the liner can collapse around the wire coil, deforming the airflow pathway 
and compromising system performance. 
Limitations of visual inspection Visual inspection is insufficient for detecting internal 
collapse, seam failure, or moisture intrusion. External insulation masks internal damage, 
and many failure modes occur within the duct wall itself. Without internal imaging or 
moisture detection, compromised systems may remain in service, compromising 
remediation efforts and exposing occupants to contaminants. 
The impracticality of duct type identification Because negative air equipment can
