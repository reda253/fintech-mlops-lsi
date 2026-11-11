import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { customersApi } from '@/api/customers';
import { MOCK_CUSTOMERS } from './mockCustomers';
import styles from './ClientFormPage.module.css';

type FormState = {
  firstName: string;
  lastName: string;
  gender: 'F' | 'M';
  birthDate: string;
  profession: string;
  street: string;
  city: string;
  state: string;
  zipCode: string;
  cityPopulation: string;
  latitude: string;
  longitude: string;
  cardNumber: string;
};

const EMPTY: FormState = {
  firstName: '',
  lastName: '',
  gender: 'F',
  birthDate: '',
  profession: '',
  street: '',
  city: '',
  state: '',
  zipCode: '',
  cityPopulation: '',
  latitude: '',
  longitude: '',
  cardNumber: '',
};

function validate(f: FormState, isEdit: boolean) {
  const errors: Partial<Record<keyof FormState, string>> = {};
  if (!f.firstName.trim()) errors.firstName = 'Champ obligatoire';
  else if (f.firstName.length > 64) errors.firstName = 'max. 64 caractères';
  if (!f.lastName.trim()) errors.lastName = 'Champ obligatoire';
  else if (f.lastName.length > 64) errors.lastName = 'max. 64 caractères';
  if (!f.birthDate) errors.birthDate = 'Champ obligatoire';
  if (!f.profession.trim()) errors.profession = 'Champ obligatoire';
  if (!f.street.trim()) errors.street = 'Champ obligatoire';
  if (!f.city.trim()) errors.city = 'Champ obligatoire';
  if (!f.state.trim()) errors.state = 'Champ obligatoire';
  else if (!/^[A-Z]{2}$/.test(f.state)) errors.state = 'Format attendu : 2 lettres majuscules (ex. NC)';
  if (!f.zipCode.trim()) errors.zipCode = 'Champ obligatoire';
  if (!f.cityPopulation.trim()) errors.cityPopulation = 'Champ obligatoire';
  if (!f.latitude.trim()) errors.latitude = 'Champ obligatoire';
  else if (Math.abs(Number(f.latitude)) > 90) errors.latitude = 'Entre -90 et 90';
  if (!f.longitude.trim()) errors.longitude = 'Champ obligatoire';
  else if (Math.abs(Number(f.longitude)) > 180) errors.longitude = 'Entre -180 et 180';
  if (!isEdit && !/^\d{12,19}$/.test(f.cardNumber)) errors.cardNumber = '12 à 19 chiffres';
  return errors;
}

export function ClientFormPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [form, setForm] = useState<FormState>(EMPTY);
  const [last4, setLast4] = useState('');
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  /* Chargement de la fiche en mode édition */
  useEffect(() => {
    if (!id) return;
    let alive = true;
    (async () => {
      try {
        const res = await customersApi.get(id);
        if (!alive) return;
        const c = res.customer;
        setForm({
          firstName: c.firstName,
          lastName: c.lastName,
          gender: c.gender,
          birthDate: c.birthDate.slice(0, 10),
          profession: c.profession,
          street: c.street,
          city: c.city,
          state: c.state,
          zipCode: c.zipCode,
          cityPopulation: String(c.cityPopulation),
          latitude: String(c.latitude),
          longitude: String(c.longitude),
          cardNumber: '',
        });
        setLast4(c.cardLast4);
      } catch {
        if (!alive) return;
        const c = MOCK_CUSTOMERS.find((x) => x.id === id) ?? MOCK_CUSTOMERS[0];
        if (!c) return;
        setForm({
          firstName: c.firstName,
          lastName: c.lastName,
          gender: c.gender,
          birthDate: c.birthDate.slice(0, 10),
          profession: c.profession,
          street: c.street,
          city: c.city,
          state: c.state,
          zipCode: c.zipCode,
          cityPopulation: String(c.cityPopulation),
          latitude: String(c.latitude),
          longitude: String(c.longitude),
          cardNumber: '',
        });
        setLast4(c.cardLast4);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  const errors = useMemo(() => (touched ? validate(form, isEdit) : {}), [form, isEdit, touched]);
  const errorCount = Object.keys(errors).length;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const outline = (key: keyof FormState) => (touched && errors[key] ? styles.inputError : '');

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setServerError(null);

    const current = validate(form, isEdit);
    if (Object.keys(current).length > 0) return;

    setSubmitting(true);
    try {
      const payload = {
        firstName: form.firstName.trim(),
        lastName: form.lastName.trim(),
        gender: form.gender,
        birthDate: form.birthDate,
        profession: form.profession.trim(),
        street: form.street.trim(),
        city: form.city.trim(),
        state: form.state.trim().toUpperCase(),
        zipCode: form.zipCode.trim(),
        cityPopulation: Number(form.cityPopulation),
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
      };
      if (isEdit && id) await customersApi.update(id, payload);
      else await customersApi.create({ ...payload, cardNumber: form.cardNumber });
      navigate(id ? PATHS.client(id) : PATHS.clients);
    } catch {
      // Mode démo : met à jour la liste en mémoire pour que la création / modification soit visible immédiatement
      const nowIso = new Date().toISOString();
      const payload = {
        firstName: form.firstName.trim(),
        lastName: form.lastName.trim(),
        gender: form.gender,
        birthDate: form.birthDate,
        profession: form.profession.trim(),
        street: form.street.trim(),
        city: form.city.trim(),
        state: form.state.trim().toUpperCase(),
        zipCode: form.zipCode.trim(),
        cityPopulation: Number(form.cityPopulation),
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
      };
      if (isEdit && id) {
        const target = MOCK_CUSTOMERS.find((x) => x.id === id);
        if (target) Object.assign(target, payload, { updatedAt: nowIso });
        navigate(PATHS.client(id));
      } else {
        const newId = `c-${String(MOCK_CUSTOMERS.length + 1).padStart(3, '0')}`;
        MOCK_CUSTOMERS.unshift({
          id: newId,
          ...payload,
          cardLast4: form.cardNumber.slice(-4),
          createdAt: nowIso,
          updatedAt: nowIso,
        });
        navigate(PATHS.clients);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* ── En-tête ─────────────────────────────────────────── */}
      <header className={styles.header}>
        <h1 className={styles.title}>{isEdit ? 'Modifier le client' : 'Nouveau client'}</h1>
        <p className={styles.subtitle}>
          {isEdit ? `${form.firstName} ${form.lastName}`.trim() || 'Client' : 'Création d’une fiche client'} · réservé aux ADMIN
        </p>
      </header>

      <form className={styles.layout} onSubmit={onSubmit} noValidate>
        {/* ── Colonne principale ────────────────────────────── */}
        <section className={styles.card}>
          {/* Identité */}
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Identité</h2>
          </div>

          <div className={styles.grid2}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="firstName">Prénom *</label>
              <input
                id="firstName"
                className={`${styles.input} ${outline('firstName')}`}
                maxLength={64}
                value={form.firstName}
                onChange={(e) => set('firstName', e.target.value)}
              />
              <span className={styles.helper}>{errors.firstName ?? 'max. 64 caractères'}</span>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="lastName">Nom *</label>
              <input
                id="lastName"
                className={`${styles.input} ${outline('lastName')}`}
                maxLength={64}
                value={form.lastName}
                onChange={(e) => set('lastName', e.target.value)}
              />
              <span className={styles.helper}>{errors.lastName ?? 'max. 64 caractères'}</span>
            </div>
          </div>

          <div className={styles.grid2}>
            <div className={styles.field}>
              <label className={styles.label}>Genre *</label>
              <div className={styles.segmented} role="group" aria-label="Genre">
                <button
                  type="button"
                  className={`${styles.segment} ${form.gender === 'F' ? styles.segmentActive : ''}`}
                  onClick={() => set('gender', 'F')}
                >
                  F
                </button>
                <button
                  type="button"
                  className={`${styles.segment} ${form.gender === 'M' ? styles.segmentActive : ''}`}
                  onClick={() => set('gender', 'M')}
                >
                  M
                </button>
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="birthDate">Date de naissance *</label>
              <input
                id="birthDate"
                type="date"
                className={`${styles.input} ${outline('birthDate')}`}
                value={form.birthDate}
                onChange={(e) => set('birthDate', e.target.value)}
              />
              {errors.birthDate && <span className={styles.error}>{errors.birthDate}</span>}
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="profession">Profession *</label>
            <input
              id="profession"
              className={`${styles.input} ${outline('profession')}`}
              value={form.profession}
              onChange={(e) => set('profession', e.target.value)}
            />
            {errors.profession && <span className={styles.error}>{errors.profession}</span>}
          </div>

          {/* Adresse */}
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Adresse</h2>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="street">Rue *</label>
            <input
              id="street"
              className={`${styles.input} ${outline('street')}`}
              value={form.street}
              onChange={(e) => set('street', e.target.value)}
            />
            {errors.street && <span className={styles.error}>{errors.street}</span>}
          </div>

          <div className={styles.grid3}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="city">Ville *</label>
              <input
                id="city"
                className={`${styles.input} ${outline('city')}`}
                value={form.city}
                onChange={(e) => set('city', e.target.value)}
              />
              {errors.city && <span className={styles.error}>{errors.city}</span>}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="state">État *</label>
              <input
                id="state"
                className={`${styles.input} ${outline('state')}`}
                maxLength={2}
                value={form.state}
                onChange={(e) => set('state', e.target.value.toUpperCase())}
              />
              {errors.state && <span className={styles.error}>{errors.state}</span>}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="zipCode">Code postal *</label>
              <input
                id="zipCode"
                className={`${styles.input} ${outline('zipCode')}`}
                value={form.zipCode}
                onChange={(e) => set('zipCode', e.target.value)}
              />
              {errors.zipCode && <span className={styles.error}>{errors.zipCode}</span>}
            </div>
          </div>

          <div className={styles.grid3}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="cityPopulation">Population de la ville *</label>
              <input
                id="cityPopulation"
                className={`${styles.input} ${outline('cityPopulation')}`}
                inputMode="numeric"
                value={form.cityPopulation}
                onChange={(e) => set('cityPopulation', e.target.value.replace(/[^\d]/g, ''))}
              />
              {errors.cityPopulation && <span className={styles.error}>{errors.cityPopulation}</span>}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="latitude">Latitude * (−90 à 90)</label>
              <input
                id="latitude"
                className={`${styles.input} ${outline('latitude')}`}
                value={form.latitude}
                onChange={(e) => set('latitude', e.target.value)}
              />
              {errors.latitude && <span className={styles.error}>{errors.latitude}</span>}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="longitude">Longitude * (−180 à 180)</label>
              <input
                id="longitude"
                className={`${styles.input} ${outline('longitude')}`}
                value={form.longitude}
                onChange={(e) => set('longitude', e.target.value)}
              />
              {errors.longitude && <span className={styles.error}>{errors.longitude}</span>}
            </div>
          </div>
        </section>

        {/* ── Colonne latérale ──────────────────────────────── */}
        <aside className={styles.side}>
          <section className={styles.card}>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>Carte bancaire</h2>
            </div>
            <div className={styles.field}>
              {isEdit ? (
                <>
                  <label className={styles.label}>Numéro de carte</label>
                  <div className={`${styles.input} ${styles.readonly}`}>
                    <span className={styles.dots}>•••• •••• ••••</span> {last4}
                  </div>
                  <span className={styles.helper}>Non modifiable : seuls les 4 derniers chiffres sont conservés</span>
                </>
              ) : (
                <>
                  <label className={styles.label} htmlFor="cardNumber">Numéro de carte *</label>
                  <input
                    id="cardNumber"
                    className={`${styles.input} ${outline('cardNumber')}`}
                    inputMode="numeric"
                    maxLength={19}
                    value={form.cardNumber}
                    onChange={(e) => set('cardNumber', e.target.value.replace(/\D/g, '').slice(0, 19))}
                  />
                  {errors.cardNumber ? (
                    <span className={styles.error}>{errors.cardNumber}</span>
                  ) : (
                    <span className={styles.helper}>12 à 19 chiffres — jamais stocké en clair</span>
                  )}
                </>
              )}
            </div>
          </section>

          {touched && errorCount > 0 && (
            <div className={styles.alert} role="alert">
              <p className={styles.alertTitle}>
                {errorCount} champ{errorCount > 1 ? 's' : ''} à corriger
              </p>
              <p className={styles.alertText}>
                Corrigez {errorCount > 1 ? 'les champs' : 'le champ'} avant d’enregistrer (erreur 400 : validation).
              </p>
            </div>
          )}

          {serverError && (
            <div className={styles.alert} role="alert">
              <p className={styles.alertTitle}>Erreur</p>
              <p className={styles.alertText}>{serverError}</p>
            </div>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={() => navigate(isEdit && id ? PATHS.client(id) : PATHS.clients)}
            >
              Annuler
            </button>
            <button type="submit" className={styles.submitBtn} disabled={submitting}>
              {submitting ? 'Enregistrement…' : 'Enregistrer'}
            </button>
          </div>

          <p className={styles.footnote}>
            À la création uniquement : numéro de carte de 12 à 19 chiffres, jamais stocké (empreinte HMAC).
            Un doublon renvoie 409.
          </p>
        </aside>
      </form>
    </div>
  );
}
