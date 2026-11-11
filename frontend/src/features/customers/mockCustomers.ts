import type { Customer, CustomerTransaction } from '@/types/customer';

/**
 * Jeu de données de démonstration — identique aux maquettes 04 / 05.
 * Utilisé quand l'API n'est pas joignable (mode « Données simulées »).
 */
const rawCustomers = [
  ['c-001', 'Emily', 'Carter', 'F', '1989-04-12', 'Data analyst', '214 Maple Grove', 'Charlotte', 'NC', '28202', 874579, 35.2271, -80.8431, '4821', '2026-08-14'],
  ['c-002', 'Marcus', 'Reed', 'M', '1976-11-02', 'Logistics manager', '18 Brickyard Rd', 'Savannah', 'GA', '31401', 147780, 32.0809, -81.0912, '7390', '2026-08-14'],
  ['c-003', 'Olivia', 'Brooks', 'F', '1994-07-21', 'Graphic designer', '77 Haywood St', 'Asheville', 'NC', '28801', 94589, 35.5951, -82.5515, '1156', '2026-08-15'],
  ['c-004', 'Daniel', 'Harper', 'M', '1982-01-30', 'Civil engineer', '502 Monument Ave', 'Richmond', 'VA', '23220', 226610, 37.5407, -77.4360, '9042', '2026-08-15'],
  ['c-005', 'Sophia', 'Nguyen', 'F', '1991-09-15', 'Pharmacist', '9 Lake Eola Dr', 'Orlando', 'FL', '32801', 307573, 28.5383, -81.3792, '3318', '2026-08-16'],
  ['c-006', 'Ethan', 'Walker', 'M', '1969-05-08', 'Retail buyer', '31 Music Row', 'Nashville', 'TN', '37203', 689447, 36.1627, -86.7816, '6274', '2026-08-16'],
  ['c-007', 'Isabella', 'Torres', 'F', '1997-12-03', 'Nurse', '412 Gervais St', 'Columbia', 'SC', '29201', 136632, 34.0007, -81.0348, '5509', '2026-08-17'],
  ['c-008', 'Noah', 'Bennett', 'M', '1985-02-26', 'Accountant', '88 High St', 'Columbus', 'OH', '43215', 905748, 39.9612, -82.9988, '2087', '2026-08-17'],
  ['c-009', 'Ava', 'Mitchell', 'F', '1979-08-19', 'Teacher', '25 Hillsborough St', 'Raleigh', 'NC', '27603', 467665, 35.7796, -78.6382, '8431', '2026-08-18'],
  ['c-010', 'Liam', 'Foster', 'M', '1988-06-11', 'Electrician', '140 Main St', 'Greenville', 'SC', '29601', 70635, 34.8526, -82.3940, '4960', '2026-08-18'],
] as const;

export const MOCK_CUSTOMERS: Customer[] = rawCustomers.map((r) => ({
  id: r[0],
  firstName: r[1],
  lastName: r[2],
  gender: r[3] as Customer['gender'],
  birthDate: r[4],
  profession: r[5],
  street: r[6],
  city: r[7],
  state: r[8],
  zipCode: r[9],
  cityPopulation: r[10],
  latitude: r[11],
  longitude: r[12],
  cardLast4: r[13],
  createdAt: `${r[14]}T09:24:00Z`,
  updatedAt: `${r[14]}T09:24:00Z`,
}));

/** Total affiché par la maquette (983 clients au global). */
export const MOCK_TOTAL = 983;

export const MOCK_TRANSACTIONS: CustomerTransaction[] = [
  { id: 't-01', reference: '613b9873', occurredAt: '2026-10-09T14:28:00Z', amount: 1329.14, currency: 'USD', category: 'shopping_net', status: 'BLOQUEE', fraudProbability: 0.93 },
  { id: 't-02', reference: 'e1ffc95d', occurredAt: '2026-10-09T14:10:00Z', amount: 555.44, currency: 'USD', category: 'grocery_pos', status: 'EN_REVUE', fraudProbability: 0.45 },
  { id: 't-03', reference: 'fc7299f5', occurredAt: '2026-10-09T13:43:00Z', amount: 209.74, currency: 'USD', category: 'shopping_net', status: 'EN_REVUE', fraudProbability: 0.62 },
  { id: 't-04', reference: '7d67bbd1', occurredAt: '2026-10-09T13:07:00Z', amount: 404.26, currency: 'USD', category: 'travel', status: 'BLOQUEE', fraudProbability: 0.5 },
  { id: 't-05', reference: 'a510b574', occurredAt: '2026-10-09T11:28:00Z', amount: 35.08, currency: 'USD', category: 'shopping_net', status: 'APPROUVEE', fraudProbability: 0.02 },
  { id: 't-06', reference: 'c261dc45', occurredAt: '2026-10-09T11:10:00Z', amount: 87.95, currency: 'USD', category: 'entertainment', status: 'APPROUVEE', fraudProbability: 0.03 },
  { id: 't-07', reference: '75f72449', occurredAt: '2026-10-09T10:43:00Z', amount: 134.76, currency: 'USD', category: 'kids_pets', status: 'APPROUVEE', fraudProbability: 0.03 },
  { id: 't-08', reference: '8d107493', occurredAt: '2026-10-09T10:07:00Z', amount: 29.22, currency: 'USD', category: 'gas_transport', status: 'APPROUVEE', fraudProbability: 0.04 },
];