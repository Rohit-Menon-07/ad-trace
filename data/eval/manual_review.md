# Manual eval cases: AWAITING HUMAN REVIEW

Drafted by Claude Code from raw Summary text (not from our extraction outputs). For each case, check the expected answer against the source sentence and change `Decision: PENDING` to `Decision: CONFIRMED` or `Decision: REJECTED`. The harness uses only CONFIRMED manual cases. After editing, re-run `make eval-freeze` and `make eval-test` (the freeze hashes this file's decisions).

## M-01 (dev)
- Query: Which proposed AD addresses loss of tightening torque on main rotor servo-controls for our AS355F1?
- Config: make=Airbus Helicopters, model=AS355F1, serial=None
- Expected: status=answered, reason=None, records=['R0001'], verdicts={'R0001': 'APPLICABLE'}, facts=[]
- Source sentence (R0001): "The FAA proposes to adopt a new airworthiness directive (AD) for all Airbus Helicopters Model AS350B3, AS355F, AS355F1, AS355F2, AS355N, AS355NP, EC130B4, and EC130T2 helicopters."
- Notes: Question mentions torque but asks which proposal exists (in scope).
- Machine check: source sentence FOUND verbatim in R0001 raw text
- Decision: PENDING

## M-02 (test)
- Query: Is there a proposal about corrosion around fasteners on the wing doublers of the P-180?
- Config: make=Baykar Piaggio Aerospace S.p.A., model=P-180, serial=None
- Expected: status=answered, reason=None, records=['R0006'], verdicts={'R0006': 'APPLICABLE'}, facts=[]
- Source sentence (R0006): "This proposed AD was prompted by a report of corrosion and cracks found around the head of attaching fasteners on main wing lower skin external reinforcement doublers."
- Notes: 'certain' P-180 airplanes
- Machine check: source sentence FOUND verbatim in R0006 raw text
- Decision: PENDING

## M-03 (dev)
- Query: What would the H160-B window jettison proposal require?
- Config: make=Airbus Helicopters, model=H160-B, serial=None
- Expected: status=answered, reason=None, records=['R0008'], verdicts={'R0008': 'APPLICABLE'}, facts=[]
- Source sentence (R0008): "This proposed AD would require removing the jettisonable windows, cleaning the ropes of the jettisonable windows, and performing an operational test of the windows jettison systems."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0008 raw text
- Decision: PENDING

## M-04 (test)
- Query: Which proposal would replace AD 2025-13-08 for the DG-1000T glider?
- Config: make=DG Aviation GmbH, model=DG-1000T, serial=None
- Expected: status=answered, reason=None, records=['R0016'], verdicts={'R0016': 'APPLICABLE'}, facts=['would supersede AD 2025-13-08']
- Source sentence (R0016): "The FAA proposes to supersede Airworthiness Directive (AD) 2025-13-08, which applies to all DG Aviation GmbH Model DG-1000T gliders."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0016 raw text; 1/1 facts' identifiers found
- Decision: PENDING

## M-05 (dev)
- Query: Does the fuel level indicator proposal cover the Vulcanair P.68B?
- Config: make=Vulcanair S.p.A., model=P.68B, serial=None
- Expected: status=answered, reason=None, records=['R0018'], verdicts={'R0018': 'APPLICABLE'}, facts=[]
- Source sentence (R0018): "The FAA proposes to adopt a new airworthiness directive (AD) for certain Vulcanair S.p.A. Model P.68 and P.68B airplanes."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0018 raw text
- Decision: PENDING

## M-06 (test)
- Query: Is there a proposed AD about the life raft bottle safety pin on the AW189?
- Config: make=Leonardo S.p.a., model=AW189, serial=None
- Expected: status=answered, reason=None, records=['R0024'], verdicts={'R0024': 'APPLICABLE'}, facts=[]
- Source sentence (R0024): "This proposed AD was prompted by reports that the safety pin of the emergency flotation system and life raft was installed on the cylinder valve of the life raft bottle assembly."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0024 raw text
- Decision: PENDING

## M-07 (test)
- Query: Is there a proposal about sliding doors jamming on the Bell 429?
- Config: make=Bell Textron Canada Limited, model=429, serial=None
- Expected: status=answered, reason=None, records=['R0029'], verdicts={'R0029': 'APPLICABLE'}, facts=[]
- Source sentence (R0029): "This proposed AD was prompted by reports of the sliding doors jamming when opened from the inside of the helicopter, due to the aft lower roller assembly disengaging from the aft lower rail."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0029 raw text
- Decision: PENDING

## M-08 (test)
- Query: Does the proposal on uncommanded nose landing gear retraction apply to the ATR72-212A?
- Config: make=None, model=ATR72-212A, serial=None
- Expected: status=answered, reason=None, records=['R0035'], verdicts={'R0035': 'APPLICABLE'}, facts=[]
- Source sentence (R0035): "The FAA proposes to adopt a new airworthiness directive (AD) for all ATR-GIE Avions de Transport R[eacute]gional Model ATR42 and ATR72 airplanes."
- Notes: Summary says 'Model ATR42 and ATR72' (types); the Model column lists ATR72-212A.
- Machine check: source sentence FOUND verbatim in R0035 raw text
- Decision: PENDING

## M-09 (test)
- Query: Does the tail boom vibration proposal apply to our Bell 206L-4?
- Config: make=Bell Textron Canada Limited, model=206L-4, serial=None
- Expected: status=answered, reason=None, records=['R0044'], verdicts={'R0044': 'UNDETERMINED'}, facts=[]
- Source sentence (R0044): "The FAA proposes to adopt a new airworthiness directive (AD) for all Bell Textron Canada Limited (Bell) Model 206L, 206L-1, 206L-3, and 206L-4 helicopters with FAA Supplemental Type Certificate (STC) SR02684LA installed."
- Notes: Applies only with STC SR02684LA installed: by reading, UNDETERMINED without knowing the STC. The engine has no STC rule (expected weakness).
- Machine check: source sentence FOUND verbatim in R0044 raw text
- Decision: PENDING

## M-10 (test)
- Query: Which proposal would supersede AD 2025-08-06?
- Config: make=None, model=None, serial=None
- Expected: status=answered, reason=None, records=['R0051'], verdicts={}, facts=['would supersede AD 2025-08-06']
- Source sentence (R0051): "The FAA proposes to supersede Airworthiness Directive (AD) 2025-08-06, which applies to certain Airbus Helicopters Model SA330J helicopters."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0051 raw text; 1/1 facts' identifiers found
- Decision: PENDING

## M-11 (test)
- Query: Is there a proposal about inspecting the emergency sea anchor on the AS332L2?
- Config: make=Airbus Helicopters, model=AS332L2, serial=None
- Expected: status=answered, reason=None, records=['R0053'], verdicts={'R0053': 'APPLICABLE'}, facts=[]
- Source sentence (R0053): "AD 2025-17-03 requires inspecting the emergency sea anchor and, depending on the result, replacing the emergency sea anchor."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0053 raw text
- Decision: PENDING

## M-12 (test)
- Query: Is there a proposed AD about the main transmission drive shaft coupling on the 500N?
- Config: make=MD Helicopters, Inc., model=500N, serial=None
- Expected: status=answered, reason=None, records=['R0083'], verdicts={'R0083': 'APPLICABLE'}, facts=[]
- Source sentence (R0083): "This proposed AD was prompted by a report of mechanical damage to the main transmission drive shaft coupling (coupling)."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0083 raw text
- Decision: PENDING

## M-13 (test)
- Query: Is there a proposal about weak ELT signals on the Cabri G2 helicopter?
- Config: make=None, model=None, serial=None
- Expected: status=answered, reason=None, records=['R0098'], verdicts={}, facts=[]
- Source sentence (R0098): "This proposed AD was prompted by a report of a potential malfunction of the helicopter emergency locator transmitter (ELT) and subsequent findings of weak ELT signals on 121.5 MHz and 406 MHz frequencies due to improper antenna installation (location)."
- Notes: No Model column; make spelled with accents.
- Machine check: source sentence FOUND verbatim in R0098 raw text
- Decision: PENDING

## M-14 (test)
- Query: Does the frame splice crack inspection proposal apply to all 757-300 airplanes?
- Config: make=The Boeing Company, model=757-300, serial=None
- Expected: status=answered, reason=None, records=['R0110'], verdicts={'R0110': 'APPLICABLE'}, facts=[]
- Source sentence (R0110): "The FAA proposes to adopt a new airworthiness directive (AD) for all The Boeing Company Model 757-300 series airplanes."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0110 raw text
- Decision: PENDING

## M-15 (test)
- Query: Is there a proposal about corroded variable geometry actuators on the CF34-8E5 engine?
- Config: make=None, model=CF34-8E5, serial=None
- Expected: status=answered, reason=None, records=['R0137'], verdicts={'R0137': 'APPLICABLE'}, facts=[]
- Source sentence (R0137): "The FAA proposes to adopt a new airworthiness directive (AD) for certain General Electric Company (GE) Model CF34-8C1, CF34-8C5, CF34-8C5A1, CF34-8C5A2, CF34-8C5B1, CF34-8E2, CF34-8E2A1, CF34-8E5, CF34-8E5A1, CF34-8E5A2, CF34-8E5A2HA, CF34-8E6, and CF34-8E6A1 engines."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0137 raw text
- Decision: PENDING

## M-16 (dev)
- Query: Is there a proposal about video monitors detaching from the PSU rails on the 737-800?
- Config: make=The Boeing Company, model=737-800, serial=None
- Expected: status=answered, reason=None, records=['R0155'], verdicts={'R0155': 'APPLICABLE'}, facts=[]
- Source sentence (R0155): "The FAA proposes to adopt a new airworthiness directive (AD) for certain The Boeing Company Model 737-600, -700, -700C, -800, -900, and 900ER series airplanes."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0155 raw text
- Decision: PENDING

## M-17 (test)
- Query: Does the PSU video monitor proposal apply to the 737-900ER?
- Config: make=The Boeing Company, model=737-900ER, serial=None
- Expected: status=answered, reason=None, records=['R0155'], verdicts={'R0155': 'APPLICABLE'}, facts=[]
- Source sentence (R0155): "The FAA proposes to adopt a new airworthiness directive (AD) for certain The Boeing Company Model 737-600, -700, -700C, -800, -900, and 900ER series airplanes."
- Notes: Source typo '900ER' (no dash); by reading it is the 737-900ER. The engine flags it LOW (expected UNDETERMINED from the system).
- Machine check: source sentence FOUND verbatim in R0155 raw text
- Decision: PENDING

## M-18 (test)
- Query: Does the wing root rib proposal now also cover the ASW-15B glider?
- Config: make=None, model=ASW-15B, serial=None
- Expected: status=answered, reason=None, records=['R0167'], verdicts={'R0167': 'APPLICABLE'}, facts=[]
- Source sentence (R0167): "This proposed AD would retain the requirements from AD 2022-14-14 of repetitively inspecting the wing root ribs for cracks, looseness, and damage and replacing any root rib with a crack, a loose rib or lift pin bushing, or any damage; and would add the Model ASW-15B gliders to the applicability."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0167 raw text
- Decision: PENDING

## M-19 (dev)
- Query: Is there a proposal about under-counted impeller cycles on the PW210S engine?
- Config: make=None, model=PW210S, serial=None
- Expected: status=answered, reason=None, records=['R0189'], verdicts={'R0189': 'APPLICABLE'}, facts=[]
- Source sentence (R0189): "The FAA proposes to adopt a new airworthiness directive (AD) for all Pratt & Whitney Canada Corp. (P&WC) PW210A and PW210S model turboshaft engines."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0189 raw text
- Decision: PENDING

## M-20 (test)
- Query: Is there a proposal about tail rotor blade life limits on the AW139?
- Config: make=None, model=AW139, serial=None
- Expected: status=answered, reason=None, records=['R0240'], verdicts={'R0240': 'APPLICABLE'}, facts=[]
- Source sentence (R0240): "We propose to supersede an existing airworthiness directive (AD) for Agusta Model AB139 and AW139 helicopters."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0240 raw text
- Decision: PENDING

## M-21 (test)
- Query: Is there a proposal about the oxygen mask supply lines on the Gulfstream 200?
- Config: make=Gulfstream Aerospace LP, model=None, serial=None
- Expected: status=answered, reason=None, records=['R0356'], verdicts={}, facts=[]
- Source sentence (R0356): "This proposed AD would require repetitive inspections for damage of the flexible supply lines of the pilot and copilot oxygen mask boxes, and eventual replacement of the lines with new rigid tubes."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0356 raw text
- Decision: PENDING

## M-22 (test)
- Query: Was the JT8D fuel nozzle borescope inspection proposal withdrawn?
- Config: make=None, model=None, serial=None
- Expected: status=answered, reason=None, records=['R0430'], verdicts={}, facts=['WITHDRAWN']
- Source sentence (R0430): "This action withdraws a notice of proposed rulemaking (NPRM) that proposed a new airworthiness directive (AD), applicable to Pratt & Whitney (PW) JT8D series turbofan engines."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0430 raw text; 1/1 facts' identifiers found
- Decision: PENDING

## M-23 (dev)
- Query: Is there a proposal about missing fire-resistant sealant in the cargo bay of the H160-B?
- Config: make=Airbus Helicopters, model=H160-B, serial=None
- Expected: status=answered, reason=None, records=['R0063'], verdicts={'R0063': 'APPLICABLE'}, facts=[]
- Source sentence (R0063): "This proposed AD was prompted by a determination that a gap without fire-resistant sealant (sealant) may be present in the cargo bay near the fuel segregation box."
- Notes: -
- Machine check: source sentence FOUND verbatim in R0063 raw text
- Decision: PENDING

## M-24 (dev)
- Query: Does the Erickson tail rotor blade proposal apply to our helicopter, blade serial 64099?
- Config: make=Erickson Air-Crane Incorporated, model=None, serial=64099
- Expected: status=refused, reason=APPLICABILITY_UNDETERMINED, records=['R0296'], verdicts={}, facts=[]
- Source sentence (R0296): "If a blade assembly has a certain serial number or part marking, the AD would also require initially and repetitively inspecting the tail rotor blade for a crack in the strap and pocket areas."
- Notes: Applicability by blade serial/part marking not listed: should not be called APPLICABLE; expected refusal APPLICABILITY_UNDETERMINED (serial given).
- Machine check: source sentence FOUND verbatim in R0296 raw text
- Decision: PENDING
