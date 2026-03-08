"""PAS Assistant — Reference selector service."""

import logging

logger = logging.getLogger(__name__)


def score_corpus_entries(cadrage: dict, entries: list[dict]) -> list[dict]:
    """Score and sort corpus entries by relevance to cadrage answers.

    Args:
        cadrage: Cadrage answers from the project.
        entries: List of corpus entry dicts (with metadata).

    Returns:
        Sorted list (descending score) with 'score' field added to each entry.
    """
    scored = []
    for entry in entries:
        score = 0

        # type_prestation: +3 if cadrage type_prestation_base is contained in entry type_prestation
        base = (cadrage.get("type_prestation_base") or "").strip().lower()
        entry_type = (entry.get("type_prestation") or "").strip().lower()
        if base and entry_type and base in entry_type:
            score += 3

        # secteur_client: +2 if identical
        c_secteur = (cadrage.get("secteur_client") or "").strip().lower()
        e_secteur = (entry.get("secteur_client") or "").strip().lower()
        if c_secteur and e_secteur and c_secteur == e_secteur:
            score += 2

        # hebergement_donnees: +1 if identical
        c_heberg = (cadrage.get("hebergement_donnees") or "").strip().lower()
        e_heberg = (entry.get("hebergement_donnees") or "").strip().lower()
        if c_heberg and e_heberg and c_heberg == e_heberg:
            score += 1

        # expertise_atlassian: +1 if identical
        c_atl = cadrage.get("expertise_atlassian")
        e_atl = entry.get("expertise_atlassian")
        if c_atl is not None and e_atl is not None:
            c_atl_bool = c_atl == "Oui" if isinstance(c_atl, str) else bool(c_atl)
            e_atl_bool = bool(e_atl)
            if c_atl_bool == e_atl_bool:
                score += 1

        # sous_traitance_rgpd: +1 if identical
        c_rgpd = cadrage.get("sous_traitance_rgpd")
        e_rgpd = entry.get("sous_traitance_rgpd")
        if c_rgpd is not None and e_rgpd is not None:
            c_rgpd_bool = c_rgpd == "Oui" if isinstance(c_rgpd, str) else bool(c_rgpd)
            e_rgpd_bool = bool(e_rgpd)
            if c_rgpd_bool == e_rgpd_bool:
                score += 1

        # lieu_travail: +1 if at least one location in common
        c_lieu = cadrage.get("lieu_travail", [])
        if isinstance(c_lieu, str):
            c_lieu = [c_lieu]
        e_lieu = entry.get("lieu_travail", [])
        if isinstance(e_lieu, str):
            e_lieu = [e_lieu]
        c_lieu_set = {loc.strip().lower() for loc in c_lieu if loc}
        e_lieu_set = {loc.strip().lower() for loc in e_lieu if loc}
        if c_lieu_set and e_lieu_set and c_lieu_set & e_lieu_set:
            score += 1

        # poste_travail: +1 if identical
        c_poste = (cadrage.get("poste_travail") or "").strip().lower()
        e_poste = (entry.get("poste_travail") or "").strip().lower()
        if c_poste and e_poste and c_poste == e_poste:
            score += 1

        scored.append({**entry, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    logger.debug("Scored %d corpus entries", len(scored))
    return scored
