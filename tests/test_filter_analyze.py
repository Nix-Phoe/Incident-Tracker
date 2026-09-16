"""
test_filter_analyze.py
=======================

Tests unitaires pour src/filter_analyze.py, écrits avec pytest.

Pourquoi commencer les tests par CE module précisément :
------------------------------------------------------------
Toutes les fonctions de filter_analyze.py sont des fonctions "pures" :
pour les mêmes entrées, elles retournent toujours la même sortie, sans
effet de bord (pas d'appel réseau, pas d'écriture de fichier). C'est le
type de fonction le PLUS FACILE à tester : pas besoin de "simuler"
(mocker) quoi que ce soit, on donne une entrée fabriquée à la main et on
vérifie la sortie.

À l'inverse, fetch_cves.py fait de vrais appels réseau -- le tester
correctement demanderait de "mocker" (simuler) la librairie `requests`
pour ne pas dépendre d'Internet ni du NVD à chaque lancement des tests.
C'est une étape plus avancée, qu'on pourra ajouter ensuite dans un fichier
tests/test_fetch_cves.py séparé.

Comment lancer ces tests :
------------------------------
    python -m pytest tests/test_filter_analyze.py -v

(on utilise `python -m pytest` plutôt que juste `pytest` pour être sûr
que le dossier du projet est bien ajouté au chemin de recherche des
imports Python -- sinon `from src.filter_analyze import ...` peut échouer
selon comment pytest est invoqué.)

Structure de chaque test : le pattern "Arrange - Act - Assert"
-------------------------------------------------------------------
Chaque test suit la même structure en 3 temps, une convention très
répandue en tests unitaires :
    1. Arrange : préparer les données d'entrée (le "contexte" du test)
    2. Act     : appeler la fonction qu'on veut tester
    3. Assert  : vérifier que le résultat est celui attendu
"""

import pandas as pd

from src.filter_analyze import (
    extraire_score_cvss,
    extraire_description,
    classifier_severite,
    transformer_en_dataframe,
    filtrer_par_score_minimum,
    filtrer_par_mot_cle,
    calculer_statistiques,
    top_n_plus_critiques,
)


# ---------------------------------------------------------------------------
# FONCTION UTILITAIRE DE TEST (pas un test elle-même, d'où l'absence du
# préfixe "test_" dans son nom -- pytest ne la lancera donc pas toute seule).
# ---------------------------------------------------------------------------

def creer_cve_de_test(
    id_cve: str = "CVE-2026-00001",
    score: float | None = None,
    version_cvss: str = "cvssMetricV31",
    description: str = "Description de test.",
    langue: str = "en",
) -> dict:
    """
    Construit une fausse CVE brute, avec la même structure imbriquée que
    celle réellement renvoyée par l'API du NVD (voir un exemple réel dans
    data/raw/ après avoir lancé fetch_cves.py).

    Fabriquer ses propres données de test plutôt que de dépendre d'un
    vrai fichier JSON est important : ça rend le test **déterministe**
    (toujours le même résultat, peu importe ce que le NVD publie demain)
    et **indépendant du réseau** (le test doit pouvoir tourner hors ligne).
    """
    cve = {
        "cve": {
            "id": id_cve,
            "published": "2026-08-19T12:00:00.000",
            "descriptions": [{"lang": langue, "value": description}],
            "metrics": {},
        }
    }

    if score is not None:
        cve["cve"]["metrics"][version_cvss] = [{"cvssData": {"baseScore": score}}]

    return cve


# ---------------------------------------------------------------------------
# Tests de extraire_score_cvss
# ---------------------------------------------------------------------------

def test_extraire_score_cvss_avec_v31():
    """Le cas le plus courant : une CVE récente avec un score CVSS v3.1."""
    cve = creer_cve_de_test(score=9.8, version_cvss="cvssMetricV31")
    assert extraire_score_cvss(cve) == 9.8


def test_extraire_score_cvss_prefere_v31_a_v2():
    """
    Si une CVE a À LA FOIS un score v3.1 et un score v2 (ça arrive : le
    NVD garde parfois l'ancien score par rétrocompatibilité), on doit
    toujours préférer le plus récent (v3.1), car c'est le plus précis.
    """
    cve = creer_cve_de_test(score=9.8, version_cvss="cvssMetricV31")
    # On ajoute manuellement un score v2 différent, pour vérifier lequel
    # des deux la fonction choisit.
    cve["cve"]["metrics"]["cvssMetricV2"] = [{"cvssData": {"baseScore": 5.0}}]

    assert extraire_score_cvss(cve) == 9.8  # et non 5.0


def test_extraire_score_cvss_sans_score_retourne_none():
    """
    Cas réel et fréquent : une CVE tout juste publiée, encore "en attente
    d'analyse" par le NVD, n'a AUCUN score. La fonction ne doit pas
    planter, elle doit retourner None -- c'est ce qui permet ensuite à
    classifier_severite() de la classer en "NON_EVALUE" plutôt que de
    faire crasher tout le pipeline sur cette seule CVE.
    """
    cve = creer_cve_de_test(score=None)
    assert extraire_score_cvss(cve) is None


# ---------------------------------------------------------------------------
# Tests de extraire_description
# ---------------------------------------------------------------------------

def test_extraire_description_en_anglais():
    cve = creer_cve_de_test(description="Un texte de description.", langue="en")
    assert extraire_description(cve) == "Un texte de description."


def test_extraire_description_sans_version_anglaise():
    """
    Cas limite : si la description en anglais manque (rarissime en
    pratique), on doit quand même retourner QUELQUE CHOSE (la première
    description disponible) plutôt que de planter.
    """
    cve = creer_cve_de_test(description="Texte en espagnol.", langue="es")
    assert extraire_description(cve) == "Texte en espagnol."


# ---------------------------------------------------------------------------
# Tests de classifier_severite
# ---------------------------------------------------------------------------
# On teste explicitement les VALEURS LIMITES (les "bornes") de chaque
# catégorie : c'est là que se cachent la plupart des bugs de logique de
# comparaison (une erreur de > au lieu de >=, par exemple).

def test_classifier_severite_critique_borne_basse():
    assert classifier_severite(9.0) == "CRITIQUE"  # exactement la borne


def test_classifier_severite_eleve_juste_sous_critique():
    assert classifier_severite(8.9) == "ELEVE"  # juste en dessous de 9.0


def test_classifier_severite_eleve_borne_basse():
    assert classifier_severite(7.0) == "ELEVE"


def test_classifier_severite_moyen_juste_sous_eleve():
    assert classifier_severite(6.9) == "MOYEN"


def test_classifier_severite_faible():
    assert classifier_severite(0.1) == "FAIBLE"


def test_classifier_severite_aucun_pour_score_zero():
    assert classifier_severite(0.0) == "AUCUN"


def test_classifier_severite_non_evalue_si_pas_de_score():
    assert classifier_severite(None) == "NON_EVALUE"


# ---------------------------------------------------------------------------
# Tests de transformer_en_dataframe
# ---------------------------------------------------------------------------

def test_transformer_en_dataframe_colonnes_attendues():
    """
    Vérifie que le DataFrame produit a bien toutes les colonnes attendues
    par le reste du pipeline (report.py en dépend directement).
    """
    cves = [creer_cve_de_test(id_cve="CVE-2026-11111", score=8.5)]
    df = transformer_en_dataframe(cves)

    colonnes_attendues = {"id", "date_publication", "score_cvss", "severite", "description", "lien"}
    assert colonnes_attendues.issubset(set(df.columns))
    assert len(df) == 1
    assert df.iloc[0]["id"] == "CVE-2026-11111"
    assert df.iloc[0]["severite"] == "ELEVE"


# ---------------------------------------------------------------------------
# Tests de filtrer_par_score_minimum
# ---------------------------------------------------------------------------

def _construire_df_de_test() -> pd.DataFrame:
    """
    Petit jeu de données de test réutilisé par plusieurs tests ci-dessous :
    3 CVE avec des scores différents (critique, moyen, et sans score).
    """
    cves = [
        creer_cve_de_test(id_cve="CVE-2026-10001", score=9.8, description="Faille dans Apache Struts."),
        creer_cve_de_test(id_cve="CVE-2026-10002", score=5.0, description="Faille dans Windows Server."),
        creer_cve_de_test(id_cve="CVE-2026-10003", score=None, description="CVE en attente d'analyse."),
    ]
    return transformer_en_dataframe(cves)


def test_filtrer_par_score_minimum_garde_seulement_au_dessus_du_seuil():
    df = _construire_df_de_test()
    df_filtre = filtrer_par_score_minimum(df, seuil=7.0)

    assert len(df_filtre) == 1
    assert df_filtre.iloc[0]["id"] == "CVE-2026-10001"


def test_filtrer_par_score_minimum_exclut_les_cve_non_evaluees():
    """
    Une CVE sans score (score_cvss = None/NaN) ne doit JAMAIS passer un
    filtre de score minimum, quel que soit le seuil -- on ne peut pas
    juger de la gravité de quelque chose qui n'a pas encore été évalué.
    """
    df = _construire_df_de_test()
    df_filtre = filtrer_par_score_minimum(df, seuil=0.0)

    ids_retenus = set(df_filtre["id"])
    assert "CVE-2026-10003" not in ids_retenus


# ---------------------------------------------------------------------------
# Tests de filtrer_par_mot_cle
# ---------------------------------------------------------------------------

def test_filtrer_par_mot_cle_trouve_la_bonne_cve():
    df = _construire_df_de_test()
    df_filtre = filtrer_par_mot_cle(df, "Apache")

    assert len(df_filtre) == 1
    assert df_filtre.iloc[0]["id"] == "CVE-2026-10001"


def test_filtrer_par_mot_cle_insensible_a_la_casse():
    """
    "windows" en minuscules doit quand même trouver "Windows Server"
    (avec un W majuscule) dans la description.
    """
    df = _construire_df_de_test()
    df_filtre = filtrer_par_mot_cle(df, "windows")

    assert len(df_filtre) == 1
    assert df_filtre.iloc[0]["id"] == "CVE-2026-10002"


def test_filtrer_par_mot_cle_none_ne_filtre_rien():
    """
    Si aucun mot-clé n'est fourni (None), le DataFrame ne doit pas être
    modifié -- c'est ce qui permet à main.py d'appeler cette fonction
    systématiquement, que l'utilisateur ait demandé un filtre ou non.
    """
    df = _construire_df_de_test()
    df_filtre = filtrer_par_mot_cle(df, None)

    assert len(df_filtre) == len(df)


# ---------------------------------------------------------------------------
# Tests de calculer_statistiques
# ---------------------------------------------------------------------------

def test_calculer_statistiques_compte_bien_chaque_severite():
    df = _construire_df_de_test()
    stats = calculer_statistiques(df)

    assert stats["total"] == 3
    assert stats["par_severite"]["CRITIQUE"] == 1
    assert stats["par_severite"]["MOYEN"] == 1
    assert stats["par_severite"]["NON_EVALUE"] == 1


# ---------------------------------------------------------------------------
# Tests de top_n_plus_critiques
# ---------------------------------------------------------------------------

def test_top_n_plus_critiques_trie_par_score_decroissant():
    df = _construire_df_de_test()
    top = top_n_plus_critiques(df, n=2)

    assert len(top) == 2
    # La CVE la plus critique (score 9.8) doit être en première position.
    assert top.iloc[0]["id"] == "CVE-2026-10001"


def test_top_n_plus_critiques_avec_n_plus_grand_que_le_nombre_de_cve():
    """
    Cas limite : demander un top 10 alors qu'il n'y a que 3 CVE ne doit
    pas planter -- on doit simplement récupérer les 3 disponibles.
    """
    df = _construire_df_de_test()
    top = top_n_plus_critiques(df, n=10)

    assert len(top) == 3
