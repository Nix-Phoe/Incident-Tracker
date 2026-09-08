# Incident Tracker (projet d'apprentissage)

Projet Python / Power BI qui simule le processus de suivi d'incidents de
sécurité d'une équipe **CSIRT** (Computer Security Incident Response
Team) : génération de tickets d'incidents, calcul d'indicateurs (KPI),
graphiques, et export d'un jeu de données propre pour un dashboard
Power BI.

> ⚠️ **Toutes les données sont synthétiques**, générées aléatoirement
> par le code (`src/generate_data.py`). Aucune vraie donnée, aucun vrai
> système, aucune vraie personne n'est impliquée. C'est un projet
> d'apprentissage.

---

## 1. Installation

Prérequis : Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate      # sous Windows (PowerShell : .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

Dépendances utilisées (volontairement minimales) : `pandas`, `numpy`,
`matplotlib`, `seaborn`, `faker`.

## 2. Utilisation

Exécuter tout le pipeline (génération → analyse → graphiques) :

```bash
python main.py
```

Options disponibles :

```bash
python main.py --n-incidents 300 --seed 123
```

- `--n-incidents` : nombre de tickets à générer (défaut : 200).
- `--seed` : graine aléatoire, pour obtenir toujours le même jeu de
  données à partir des mêmes paramètres (défaut : 42).

Chaque module peut aussi être exécuté seul, indépendamment du pipeline
(pratique pour tester ou déboguer une seule étape) :

```bash
python -m src.generate_data   # régénère seulement data/incidents.csv
python -m src.analysis        # relit incidents.csv, affiche le rapport KPI, régénère incidents_clean.csv
python -m src.visualize       # régénère seulement les graphiques
```

**Fichiers produits :**

| Fichier | Rôle |
|---|---|
| `data/incidents.csv` | Données brutes générées (une ligne = un ticket) |
| `data/incidents_clean.csv` | Données enrichies (colonnes calculées), prêtes pour Power BI |
| `outputs/figures/*.png` | 3 graphiques (tendance, répartition, temps de résolution) |

## 3. Logique de chaque module

### `src/generate_data.py` — Génération des données

Génère des tickets d'incidents avec des distributions **réalistes**,
pas uniformes :

- **Sévérité** : pondérée en pyramide (40 % faible, 35 % moyenne, 18 %
  élevée, 7 % critique) — une vraie équipe n'a jamais autant
  d'incidents critiques que d'incidents mineurs.
- **Type d'incident** : le phishing est le plus fréquent (35 %),
  cohérent avec les statistiques réelles sur les vecteurs d'attaque
  initiaux.
- **Temps de résolution** : tiré d'une loi **log-normale** dont la
  médiane dépend de la sévérité (faible ≈ 4h, critique ≈ 96h). Une loi
  log-normale produit une distribution asymétrique à droite (beaucoup
  de tickets rapides, une longue traîne de tickets lents), ce qui
  reflète mieux la réalité qu'une simple moyenne fixe.
- **Statut** (ouvert / en cours / résolu / fermé) : dérivé de l'âge du
  ticket plutôt que tiré au hasard indépendamment, avec ~8 % de tickets
  qui restent volontairement bloqués (backlog réaliste, matière pour la
  détection de SLA dépassé).

### `src/analysis.py` — Nettoyage et KPI

Enrichit les données brutes avec des colonnes calculées
(`est_resolu`, `semaine_ouverture`, `sla_cible_jours`,
`jours_ouverture`, `sla_respecte`, `sla_actuellement_depasse`), puis
calcule :

- Nombre d'incidents ouverts vs résolus.
- Temps de résolution moyen **et médian** par sévérité.
- Répartition par type d'incident.
- Tendance hebdomadaire (nombre d'incidents ouverts par semaine).
- Liste des incidents **encore actifs dont le SLA est dépassé**, selon
  un seuil configurable par sévérité (`SLA_JOURS_PAR_SEVERITE` :
  critique = 1 jour, élevée = 3, moyenne = 5, faible = 10).

### `src/visualize.py` — Graphiques

Génère 3 graphiques avec matplotlib/seaborn, en réutilisant les calculs
de `analysis.py` (jamais de recalcul dupliqué) :

1. **Tendance temporelle** — courbe des incidents ouverts par semaine.
2. **Répartition type × sévérité** — barres empilées horizontales, avec
   une palette "feu de circulation" (vert → rouge) cohérente sur tout
   le projet.
3. **Temps de résolution moyen par sévérité** — barres en échelle
   logarithmique (l'écart entre "faible" et "critique" est trop grand
   pour une échelle linéaire lisible).

### `main.py` — Pipeline

Enchaîne les 3 étapes. Chaque étape lit/écrit sur disque plutôt que de
se passer les données uniquement en mémoire : ça reproduit le
fonctionnement d'un vrai pipeline batch, où chaque étape peut être
relancée ou inspectée indépendamment.

## 4. Connecter les données à Power BI

Le fichier `data/incidents_clean.csv` est pensé pour être importé
directement, sans retravailler les données dans Power BI :

1. **Power BI Desktop** → `Accueil` → `Obtenir les données` → `Texte/CSV`.
2. Sélectionner `data/incidents_clean.csv`, vérifier que l'encodage
   détecté est `UTF-8`, puis `Charger` (ou `Transformer les données`
   si tu veux ajuster les types de colonnes dans Power Query).
3. Vérifier que Power BI reconnaît bien `date_ouverture`,
   `date_resolution` et `semaine_ouverture` comme des colonnes de type
   **Date/Heure** (sinon les corriger dans Power Query).

**Visualisations suggérées** (colonnes déjà prêtes à l'emploi) :

- **Carte / carte multiligne** : total d'incidents, % résolus
  (`est_resolu`), nombre en dépassement de SLA (`sla_actuellement_depasse`).
- **Graphique en courbes** : nombre d'incidents par `semaine_ouverture`
  (axe X) — équivalent interactif du graphique de tendance.
- **Graphique à barres empilées** : `type_incident` en axe, `severite`
  en légende — équivalent du graphique de répartition.
- **Graphique à barres** : moyenne de `temps_resolution_heures` par
  `severite` (utiliser une mesure `MOYENNE` dans le panneau de champs).
- **Table ou matrice filtrable** : liste des incidents où
  `sla_actuellement_depasse = TRUE`, avec segments (slicers) sur
  `severite`, `type_incident` et `statut` pour explorer librement.
- **Jauge ou indicateur KPI** : % d'incidents avec `sla_respecte = TRUE`
  parmi les incidents résolus — un vrai indicateur de conformité SLA.

## 5. Lien avec un vrai processus CSIRT

Ce projet simplifie énormément la réalité, mais chaque étape a un
équivalent direct dans un vrai processus de réponse aux incidents :

| Dans ce projet | Dans une vraie équipe CSIRT |
|---|---|
| `generate_data.py` produit des tickets | Un outil de ticketing (ServiceNow, Jira SM, TheHive...) reçoit les alertes d'un SIEM, d'un EDR, ou des signalements utilisateurs, et crée un ticket par incident |
| Colonne `severite` | Une **classification de criticité** (souvent basée sur un cadre comme le NIST SP 800-61 ou une matrice impact × probabilité), qui détermine l'urgence de la réponse |
| Colonne `sla_cible_jours` | Un vrai **SLA de sécurité** contractuel ou interne, souvent en heures pour les incidents critiques (ex: containment sous 4h) |
| `sla_actuellement_depasse` | Un indicateur qu'un **analyste SOC ou un manager CSIRT** surveille en temps réel — un dépassement de SLA sur un incident actif est un signal d'alerte opérationnel |
| Répartition par `type_incident` | Alimente les décisions de **priorisation des investissements** en sécurité (ex: beaucoup de phishing → investir dans la sensibilisation et le filtrage email) |
| Tendance hebdomadaire | Sert à détecter une **hausse anormale** du volume d'incidents, potentiellement le signe d'une campagne d'attaque coordonnée |
| Dashboard Power BI | Le tableau de bord qu'un **RSSI (CISO)** ou un comité de direction consulterait pour évaluer la posture de sécurité globale |

En résumé : ce projet reproduit en miniature le cycle **détecter →
qualifier → prioriser → traiter → mesurer** qui est au cœur de tout
processus de réponse aux incidents, avec les mêmes types de questions
qu'un vrai CSIRT se pose (combien d'incidents sont en retard ? quel
type d'attaque domine ? le temps de réponse s'améliore-t-il ?).
